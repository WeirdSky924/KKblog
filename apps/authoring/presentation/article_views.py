from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.authoring.forms import ArticleDeleteForm, ArticleRestoreForm
from apps.authoring.presenters import article_workspace
from apps.content.public import (
    ArticleDeletionError,
    ArticleNotFound,
    delete_article,
    restore_deleted_article,
)
from apps.core.http import is_htmx_fragment_request

from .access import author_id_or_response, private_response

_DELETE_ERRORS = {
    "invalid": "删除确认已失效，请刷新页面后重试。",
    "conflict": "文章版本已经变化，请确认最新状态后重试。",
    "failed": "暂时无法删除这篇文章，请重试。",
}

_RESTORE_ERRORS = {
    "invalid": "恢复确认已失效，请刷新页面后重试。",
    "conflict": "文章版本已经变化，请刷新后重试。",
    "expired": "文章恢复期限已结束，当前不能恢复。",
    "failed": "暂时无法恢复这篇文章，请重试。",
}


def _articles_url(*, state: str, page: int, **flags: str) -> str:
    query = {"state": state, "page": page, **flags}
    return f"{reverse('authoring:articles')}?{urlencode(query)}"


def _workspace_response(
    request,
    *,
    actor_id,
    state: str,
    page: int,
    deleted: bool = False,
    restored: bool = False,
    error: str = "",
    restore_error: str = "",
    status: int = 200,
):
    if not is_htmx_fragment_request(request):
        flags = (
            {"deleted": "1"}
            if deleted
            else {"restored": "1"}
            if restored
            else {"restore_error": restore_error}
            if restore_error
            else {"delete_error": error}
        )
        return private_response(
            redirect(_articles_url(state=state, page=page, **flags))
        )
    workspace = article_workspace(actor_id=actor_id, state=state, page=page)
    response = render(
        request,
        "authoring/partials/article_workspace.html",
        {
            "workspace": workspace,
            "pagination_query": urlencode({"state": workspace.selected_state}),
            "article_deleted": deleted,
            "article_restored": restored,
            "article_delete_error": _DELETE_ERRORS.get(error, ""),
            "article_restore_error": _RESTORE_ERRORS.get(restore_error, ""),
        },
        status=status,
    )
    response.headers["HX-Push-Url"] = _articles_url(state=state, page=page)
    return private_response(response)


def articles(request):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    try:
        workspace = article_workspace(
            actor_id=actor_id,
            state=request.GET.get("state", "PUBLISHED"),
            page=request.GET.get("page", 1),
        )
    except ArticleNotFound:
        raise PermissionDenied from None
    except ValueError:
        raise Http404 from None
    if request.method != "GET":
        return private_response(HttpResponseNotAllowed(("GET",)))
    template = (
        "authoring/partials/article_workspace.html"
        if is_htmx_fragment_request(request)
        else "authoring/articles.html"
    )
    return private_response(
        render(
            request,
            template,
            {
                "workspace": workspace,
                "pagination_query": urlencode({"state": workspace.selected_state}),
                "article_deleted": request.GET.get("deleted") == "1",
                "article_restored": request.GET.get("restored") == "1",
                "article_delete_error": _DELETE_ERRORS.get(
                    request.GET.get("delete_error", ""), ""
                ),
                "article_restore_error": _RESTORE_ERRORS.get(
                    request.GET.get("restore_error", ""), ""
                ),
            },
        )
    )


def delete_article_from_list(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    form = ArticleDeleteForm(request.POST)
    if not form.is_valid():
        return _workspace_response(
            request,
            actor_id=actor_id,
            state="PUBLISHED",
            page=1,
            error="invalid",
            status=422,
        )
    values = form.cleaned_data
    try:
        delete_article(
            actor_id=actor_id,
            article_id=article_id,
            expected_row_version=values["expected_row_version"],
            administrative=False,
            trace_code=getattr(request, "trace_code", ""),
            client_ip=request.client_ip,
        )
    except ArticleDeletionError as exc:
        if exc.code == "content.article_delete_not_allowed.v1":
            raise Http404 from None
        error = "conflict" if exc.code == "content.edit_conflict.v1" else "failed"
        return _workspace_response(
            request,
            actor_id=actor_id,
            state=values["return_state"],
            page=values["return_page"],
            error=error,
            status=409 if error == "conflict" else 422,
        )
    return _workspace_response(
        request,
        actor_id=actor_id,
        state=values["return_state"],
        page=values["return_page"],
        deleted=True,
    )


def restore_article_from_list(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    form = ArticleRestoreForm(request.POST)
    if not form.is_valid():
        return _workspace_response(
            request,
            actor_id=actor_id,
            state="DELETED",
            page=1,
            restore_error="invalid",
            status=422,
        )
    values = form.cleaned_data
    try:
        restoration = restore_deleted_article(
            actor_id=actor_id,
            article_id=article_id,
            expected_row_version=values["expected_row_version"],
            trace_code=getattr(request, "trace_code", ""),
            client_ip=request.client_ip,
        )
    except ArticleDeletionError as exc:
        if exc.code == "content.article_restore_not_allowed.v1":
            raise Http404 from None
        if exc.code == "content.article_restore_expired.v1":
            error = "expired"
        elif exc.code == "content.edit_conflict.v1":
            error = "conflict"
        else:
            error = "failed"
        return _workspace_response(
            request,
            actor_id=actor_id,
            state=values["return_state"],
            page=values["return_page"],
            restore_error=error,
            status=409 if error == "conflict" else 422,
        )
    return _workspace_response(
        request,
        actor_id=actor_id,
        state=restoration.publication_state,
        page=1,
        restored=True,
    )
