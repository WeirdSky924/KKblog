from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.content.public import ArticleLoginRequired, ArticleNotFound

from .cooldown import CommentCooldownUnavailable
from .errors import CommentPostingError
from .http import is_htmx, posting_status
from .models import Comment
from .policies import CommentDeletionMode, comment_deletion_mode
from .presentation import (
    ReplyCommentForm,
    comment_context_for_target,
)
from .presentation.deletion_forms import CommentDeletionForm
from .queries import CommentCursorError, comment_thread_access, public_reply_page
from .services import GuestbookUnavailableError, reply_to_comment
from .services.deletion import (
    CommentDeletionError,
    delete_comment_as_admin,
    delete_comment_as_owner,
    delete_own_comment,
)


def _context(request, comment: Comment, **kwargs):
    try:
        return comment_context_for_target(
            request=request,
            target_type=comment.thread.target_type,
            target_id=comment.thread.target_id,
            **kwargs,
        )
    except (ArticleLoginRequired, ArticleNotFound, GuestbookUnavailableError):
        raise Http404 from None


def _panel_response(request, context, *, status: int):
    if is_htmx(request):
        template = "comments/partials/thread_panel.html"
    elif context["comment_target_type"] == "GUESTBOOK":
        template = "comments/thread_page.html"
    else:
        template = "comments/article_comment_form_page.html"
    response = render(request, template, context, status=status)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _capability(
    request,
    *,
    comment_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
):
    comment = Comment.objects.select_related("thread").filter(pk=comment_id).first()
    if comment is None:
        raise Http404
    if target_type is not None and (
        comment.thread.target_type != target_type
        or comment.thread.target_id != target_id
    ):
        raise Http404
    try:
        access = comment_thread_access(
            actor_id=getattr(request, "account_id", None),
            target_type=comment.thread.target_type,
            target_id=comment.thread.target_id,
        )
    except (ArticleLoginRequired, ArticleNotFound, GuestbookUnavailableError):
        raise Http404 from None
    if access.thread_id != str(comment.thread_id):
        raise Http404
    return comment, access


def _requested_mode(value) -> CommentDeletionMode:
    try:
        return CommentDeletionMode(value)
    except (TypeError, ValueError):
        raise Http404 from None


def _deletion_capability(request, **kwargs):
    comment, access = _capability(request, **kwargs)
    mode = comment_deletion_mode(
        state=comment.state,
        author_kind=comment.author_kind,
        author_id=comment.author_id,
        actor_id=access.actor_id,
        thread_owner_id=access.owner_id,
        is_administrator=access.is_administrator,
    )
    if mode is None:
        raise Http404
    return comment, mode


def _delete_dialog(request, *, comment, mode, form, delete_url, status=200):
    noun = "留言" if comment.thread.target_type == "GUESTBOOK" else "评论"
    title = {
        CommentDeletionMode.SELF: f"删除自己的{noun}？",
        CommentDeletionMode.OWNER: f"删除这条{noun}？",
        CommentDeletionMode.ADMIN: f"管理员删除这条{noun}？",
    }[mode]
    description = (
        "这是终局操作，删除后不能申诉；现有回复仍会保留。"
        if mode == CommentDeletionMode.ADMIN
        else "删除后会保留占位，现有回复不会消失。"
    )
    response = render(
        request,
        "comments/partials/delete_dialog.html",
        {
            "comment": comment,
            "deletion_mode": mode,
            "deletion_form": form,
            "dialog_title": title,
            "dialog_description": description,
            "delete_url": delete_url,
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    if status == 422:
        response.headers["HX-Retarget"] = "#comment-dialog-host"
        response.headers["HX-Reswap"] = "innerHTML"
    return response


def confirm_comment_delete_for_target(request, *, delete_url: str, **kwargs):
    comment, mode = _deletion_capability(request, **kwargs)
    if _requested_mode(request.GET.get("mode")) != mode:
        raise Http404
    return _delete_dialog(
        request,
        comment=comment,
        mode=mode,
        form=CommentDeletionForm(initial={"mode": mode.value}),
        delete_url=delete_url,
    )


def delete_comment_for_target(request, *, delete_url: str, **kwargs):
    comment, mode = _deletion_capability(request, **kwargs)
    if _requested_mode(request.POST.get("mode")) != mode:
        raise Http404
    form = CommentDeletionForm(request.POST)
    if not form.is_valid():
        return _delete_dialog(
            request,
            comment=comment,
            mode=mode,
            form=form,
            delete_url=delete_url,
            status=422,
        )
    command = {
        CommentDeletionMode.SELF: delete_own_comment,
        CommentDeletionMode.OWNER: delete_comment_as_owner,
        CommentDeletionMode.ADMIN: delete_comment_as_admin,
    }[mode]
    command_kwargs = {
        "comment_id": comment.id,
        "actor_id": getattr(request, "account_id", None),
        "client_ip": request.client_ip,
        "trace_code": request.trace_code,
    }
    if mode == CommentDeletionMode.ADMIN:
        command_kwargs["reason"] = form.cleaned_data["reason"]
    try:
        command(**command_kwargs)
    except CommentDeletionError as exc:
        if exc.code == "comments.deletion_reason_invalid.v1":
            form.add_error("reason", exc.safe_message)
            return _delete_dialog(
                request,
                comment=comment,
                mode=mode,
                form=form,
                delete_url=delete_url,
                status=422,
            )
        if exc.code != "comments.media_cleanup_failed.v1":
            raise Http404 from None
        context = _context(request, comment)
        context["comment_system_error"] = exc.safe_message
        context["comment_trace_code"] = request.trace_code
        return _panel_response(request, context, status=503)
    context = _context(
        request,
        comment,
        feedback=f"{('留言' if comment.thread.target_type == 'GUESTBOOK' else '评论')}已删除。",
    )
    if not is_htmx(request):
        return HttpResponseRedirect(f"{context['comment_return_url']}#comment-thread")
    return _panel_response(request, context, status=200)


@require_GET
def confirm_comment_delete(request, comment_id):
    return confirm_comment_delete_for_target(
        request,
        comment_id=comment_id,
        delete_url=reverse(
            "comments:comment-delete", kwargs={"comment_id": comment_id}
        ),
    )


@require_POST
def delete_comment(request, comment_id):
    return delete_comment_for_target(
        request,
        comment_id=comment_id,
        delete_url=reverse(
            "comments:comment-delete", kwargs={"comment_id": comment_id}
        ),
    )


def _reply_capability(request, *, comment_id: str):
    comment, access = _capability(request, comment_id=comment_id)
    if (
        not access.is_active_actor
        or not access.comments_enabled
        or comment.state == Comment.State.DELETED
    ):
        raise Http404
    return comment


def _reply_dialog(request, *, comment, form, status=200):
    noun = "留言" if comment.thread.target_type == "GUESTBOOK" else "评论"
    response = render(
        request,
        "comments/partials/reply_dialog.html",
        {
            "comment": comment,
            "comment_noun": noun,
            "reply_form": form,
            "reply_url": reverse(
                "comments:comment-reply", kwargs={"comment_id": comment.id}
            ),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    if status in {422, 429}:
        response.headers["HX-Retarget"] = "#comment-dialog-host"
        response.headers["HX-Reswap"] = "innerHTML"
    return response


@require_GET
def confirm_comment_reply(request, comment_id):
    comment = _reply_capability(request, comment_id=comment_id)
    return _reply_dialog(
        request,
        comment=comment,
        form=ReplyCommentForm(auto_id=f"comment-reply-{comment.id}-%s"),
    )


@require_POST
def create_comment_reply(request, comment_id):
    comment = _reply_capability(request, comment_id=comment_id)
    form = ReplyCommentForm(
        request.POST,
        auto_id=f"comment-reply-{comment.id}-%s",
    )
    if not form.is_valid():
        return _reply_dialog(request, comment=comment, form=form, status=422)
    try:
        reply_to_comment(
            parent_id=comment.id,
            actor_id=getattr(request, "account_id", None),
            client_ip=request.client_ip,
            body=form.cleaned_data["body"],
            trace_code=request.trace_code,
        )
    except CommentCooldownUnavailable:
        context = _context(request, comment)
        context["comment_system_error"] = "回复服务暂时不可用，请稍后重试。"
        context["comment_trace_code"] = request.trace_code
        return _panel_response(request, context, status=503)
    except CommentPostingError as exc:
        status = posting_status(exc.code)
        if status == 404:
            raise Http404 from None
        form.add_error(None, exc.safe_message)
        response = _reply_dialog(request, comment=comment, form=form, status=status)
        if exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response
    context = _context(request, comment, feedback="回复已提交，将在 10 分钟后公开。")
    if not is_htmx(request):
        return HttpResponseRedirect(f"{context['comment_return_url']}#comment-thread")
    return _panel_response(request, context, status=201)


def _comment_list_error(request):
    response = render(
        request,
        "comments/partials/list_error.html",
        {"comment_list_error": "评论列表未能继续加载，请刷新页面重试。"},
        status=422,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def comment_replies_for_target(
    request,
    *,
    root_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
):
    root, access = _capability(
        request,
        comment_id=root_id,
        target_type=target_type,
        target_id=target_id,
    )
    if root.parent_id is not None:
        raise Http404
    try:
        page = public_reply_page(
            thread_id=access.thread_id,
            can_view=access.can_view,
            root_id=root.id,
            cursor=request.GET.get("cursor") or None,
            actor_id=access.actor_id,
            thread_owner_id=access.owner_id,
            is_administrator=access.is_administrator,
            can_reply=access.is_active_actor and access.comments_enabled,
            can_report=access.is_active_actor,
        )
    except CommentCursorError:
        return _comment_list_error(request)
    response = render(
        request,
        "comments/partials/reply_batch.html",
        {
            "reply_page": page,
            "comment_root_id": root.id,
            "comment_target_type": root.thread.target_type,
            "comment_article_id": (
                root.thread.target_id if root.thread.target_type == "ARTICLE" else None
            ),
            "comment_noun": (
                "留言" if root.thread.target_type == "GUESTBOOK" else "评论"
            ),
            "focus_reply_batch": True,
        },
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def comment_replies(request, root_id):
    return comment_replies_for_target(request, root_id=root_id)
