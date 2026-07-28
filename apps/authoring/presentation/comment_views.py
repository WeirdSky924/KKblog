from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.authoring.operation_forms import (
    ArticleCommentsToggleForm,
    ManagedCommentDeleteForm,
)
from apps.authoring.presenters import comment_workspace_page
from apps.comments.public import (
    ArticleCommentSettingsError,
    CommentCursorError,
    CommentDeletionError,
    article_comment_access,
    article_comment_panel,
    delete_article_comment_as_owner,
    public_reply_page,
    set_article_comments_enabled,
)
from apps.content.public import ArticleNotFound, article_for_author

from .access import author_id_or_response, private_response


def _method(request, allowed):
    if request.method not in allowed:
        return private_response(HttpResponseNotAllowed(allowed))
    return None


def _workspace(actor_id):
    return comment_workspace_page(actor_id=actor_id)


def _article_and_panel(*, actor_id, article_id: str, sort="earliest", cursor=None):
    try:
        article = article_for_author(actor_id=actor_id, article_id=article_id)
        panel = article_comment_panel(
            actor_id=actor_id,
            article_id=article_id,
            sort=sort,
            cursor=cursor,
        )
    except (ArticleNotFound, CommentCursorError):
        raise Http404 from None
    return article, panel


def comments_buffer(request):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET",)):
        return denied
    return private_response(
        render(
            request,
            "authoring/comments.html",
            {
                "comments_tab": "buffer",
                "comment_workspace": _workspace(actor_id),
                "comment_deleted": request.GET.get("deleted") == "1",
                "comment_confirm_id": request.GET.get("confirm", ""),
            },
        )
    )


def comments_articles(request):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET",)):
        return denied
    selected_id = request.GET.get("article", "")
    article = None
    panel = None
    if selected_id:
        article, panel = _article_and_panel(
            actor_id=actor_id,
            article_id=selected_id,
            sort=request.GET.get("sort", "earliest"),
            cursor=request.GET.get("cursor") or None,
        )
    return private_response(
        render(
            request,
            "authoring/comments.html",
            {
                "comments_tab": "articles",
                "comment_workspace": _workspace(actor_id),
                "managed_article": article,
                "managed_comment_panel": panel,
                "managed_comment_sort": request.GET.get("sort", "earliest"),
                "comment_deleted": request.GET.get("deleted") == "1",
                "comment_settings_saved": request.GET.get("settings") == "1",
                "comment_confirm_id": request.GET.get("confirm", ""),
            },
        )
    )


def comments_article_page(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET",)):
        return denied
    ordering = request.GET.get("sort", "earliest")
    _, panel = _article_and_panel(
        actor_id=actor_id,
        article_id=article_id,
        sort=ordering,
        cursor=request.GET.get("cursor") or None,
    )
    return private_response(
        render(
            request,
            "authoring/partials/managed_root_batch.html",
            {
                "managed_article_id": article_id,
                "managed_comment_page": panel.public_page,
                "managed_comment_sort": ordering,
            },
        )
    )


def comments_article_replies(request, article_id: str, root_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET",)):
        return denied
    try:
        article_for_author(actor_id=actor_id, article_id=article_id)
        access = article_comment_access(actor_id=actor_id, article_id=article_id)
        page = public_reply_page(
            thread_id=access.thread_id,
            can_view=True,
            root_id=root_id,
            cursor=request.GET.get("cursor") or None,
            actor_id=actor_id,
            thread_owner_id=access.owner_id,
            can_reply=False,
            can_report=False,
        )
    except (ArticleNotFound, CommentCursorError):
        raise Http404 from None
    return private_response(
        render(
            request,
            "authoring/partials/managed_reply_batch.html",
            {
                "managed_article_id": article_id,
                "managed_reply_root_id": root_id,
                "managed_reply_page": page,
            },
        )
    )


def toggle_article_comments(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("POST",)):
        return denied
    form = ArticleCommentsToggleForm(request.POST)
    if not form.is_valid():
        raise Http404
    try:
        set_article_comments_enabled(
            actor_id=actor_id,
            article_id=article_id,
            enabled=form.cleaned_data["enabled"],
        )
    except ArticleCommentSettingsError:
        raise Http404 from None
    url = reverse("authoring:comments-article")
    return redirect(f"{url}?article={article_id}&settings=1#managed-comments")


def delete_managed_comment(request, article_id: str, comment_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("POST",)):
        return denied
    form = ManagedCommentDeleteForm(request.POST)
    if not form.is_valid():
        raise Http404
    try:
        delete_article_comment_as_owner(
            actor_id=actor_id,
            article_id=article_id,
            comment_id=comment_id,
            client_ip=request.client_ip,
            trace_code=request.trace_code,
        )
    except CommentDeletionError:
        raise Http404 from None
    if request.POST.get("return_to") == "buffer":
        url = reverse("authoring:comments-buffer")
    else:
        url = f"{reverse('authoring:comments-article')}?article={article_id}"
    separator = "&" if "?" in url else "?"
    return redirect(f"{url}{separator}deleted=1#managed-comments")
