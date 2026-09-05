from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.accounts.public import is_administrator
from apps.administration.forms.moderation import CommentDeletionConfirmationForm
from apps.administration.presentation.moderation import (
    admin_comment_rows,
    admin_comment_thread_rows,
    article_title_map,
    target_label,
)
from apps.comments.public import (
    AdminCommentNotFound,
    CommentDeletionError,
    admin_comment_detail,
    admin_comment_workspace,
    admin_comments_for_target,
    delete_comment_as_admin,
)
from apps.content.public import admin_article_titles

VALID_TABS = {"buffered", "threads"}


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _comment(request: HttpRequest, comment_id: str):
    try:
        return admin_comment_detail(
            actor_id=request.account_id,
            comment_id=comment_id,
        )
    except (AdminCommentNotFound, PermissionError):
        raise Http404 from None


def _confirmation(request: HttpRequest):
    comment_id = request.GET.get("confirm", "")
    if not comment_id:
        return None, None
    detail = _comment(request, comment_id)
    if detail.state == "DELETED":
        raise Http404
    return detail, CommentDeletionConfirmationForm(
        initial={"comment_id": detail.id, "confirm": "comment_delete"}
    )


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    confirmation_detail=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    tab = request.GET.get("tab", "buffered")
    if tab not in VALID_TABS:
        tab = "buffered"
        page_error = "评论管理视图无效。"
        status = 422
    selected_type = request.GET.get("target_type", "")
    selected_id = request.GET.get("target_id", "")
    try:
        workspace = admin_comment_workspace(
            actor_id=request.account_id,
            buffered_page=(
                _page_number(request.GET.get("buffered_page"))
                if tab == "buffered"
                else None
            ),
            thread_page=(
                _page_number(request.GET.get("thread_page"))
                if tab == "threads"
                else None
            ),
            page_size=20,
            include_buffered=tab == "buffered",
            include_threads=tab == "threads",
        )
        article_ids = tuple(
            row.target_id
            for row in (*workspace.buffered_items, *workspace.threads)
            if row.target_type == "ARTICLE"
        )
        if selected_type == "ARTICLE" and selected_id:
            article_ids = (*article_ids, selected_id)
        articles = admin_article_titles(
            actor_id=request.account_id,
            article_ids=article_ids,
        )
    except PermissionError:
        raise PermissionDenied from None
    except ValueError as exc:
        page_error = str(exc)
        status = 422
        workspace = None
        articles = ()
    titles = article_title_map(articles)

    comments = ()
    if selected_type or selected_id:
        if not selected_type or not selected_id:
            raise Http404
        try:
            comments = admin_comments_for_target(
                actor_id=request.account_id,
                target_type=selected_type,
                target_id=selected_id,
                page=_page_number(request.GET.get("target_page")),
                page_size=20,
            )
        except AdminCommentNotFound:
            raise Http404 from None

    detail = None
    detail_id = request.GET.get("detail", "")
    if detail_id:
        detail = _comment(request, detail_id)

    buffered = workspace.buffered_items if workspace is not None else ()
    threads = workspace.threads if workspace is not None else ()
    comment_page = comments if hasattr(comments, "items") else None
    return_url = f"{reverse('admin:comments')}?tab={tab}#comment-workspace"
    response = render(
        request,
        "administration/comments.html",
        {
            "tab": tab,
            "buffered_rows": admin_comment_rows(
                comments=buffered,
                titles=titles,
            ),
            "thread_rows": admin_comment_thread_rows(
                threads=threads,
                titles=titles,
            ),
            "comment_rows": admin_comment_rows(
                comments=comment_page.items if comment_page is not None else comments,
                titles=titles,
            ),
            "buffered_page": workspace.buffered_page if workspace is not None else None,
            "thread_page": workspace.thread_page if workspace is not None else None,
            "comment_page": comment_page,
            "buffered_pagination_query": "tab=buffered",
            "thread_pagination_query": "tab=threads",
            "comment_pagination_query": urlencode(
                {
                    "tab": "threads",
                    "target_type": selected_type,
                    "target_id": selected_id,
                }
            )
            if selected_type and selected_id
            else "",
            "selected_type": selected_type,
            "selected_id": selected_id,
            "selected_label": (
                target_label(
                    target_type=selected_type,
                    target_id=selected_id,
                    titles=titles,
                )
                if selected_type and selected_id
                else ""
            ),
            "detail": detail,
            "detail_label": (
                target_label(
                    target_type=detail.target_type,
                    target_id=detail.target_id,
                    titles=titles,
                )
                if detail is not None
                else ""
            ),
            "confirmation_detail": confirmation_detail,
            "confirmation_form": confirmation_form,
            "confirmation_return_url": return_url,
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _post(request: HttpRequest) -> HttpResponse:
    form = CommentDeletionConfirmationForm(request.POST)
    if request.POST.get("action", "") != "comment_delete":
        return _render(request, status=422, page_error="评论管理操作无效。")
    if not form.is_valid():
        try:
            detail = _comment(request, request.POST.get("comment_id", ""))
        except Http404:
            return _render(request, status=422, page_error="请重新确认评论删除。")
        return _render(
            request,
            status=422,
            confirmation_detail=detail,
            confirmation_form=form,
        )
    detail = _comment(request, form.cleaned_data["comment_id"])
    try:
        delete_comment_as_admin(
            actor_id=request.account_id,
            comment_id=form.cleaned_data["comment_id"],
            reason=form.cleaned_data["reason"],
            client_ip=request.client_ip,
            trace_code=getattr(request, "trace_code", ""),
        )
    except CommentDeletionError as exc:
        form.add_error("reason" if "reason" in exc.code else None, exc.safe_message)
        return _render(
            request,
            status=403 if "not_allowed" in exc.code else 422,
            confirmation_detail=detail,
            confirmation_form=form,
        )
    return redirect(
        f"{reverse('admin:comments')}?saved=deleted&tab=threads"
        f"&target_type={detail.target_type}&target_id={detail.target_id}"
        "#target-comments"
    )


def comments(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "POST":
        return _post(request)
    detail, form = _confirmation(request)
    return _render(
        request,
        confirmation_detail=detail,
        confirmation_form=form,
    )


__all__ = ["comments"]
