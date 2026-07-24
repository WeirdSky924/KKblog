from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.content.public import ArticleLoginRequired, ArticleNotFound

from .cooldown import CommentCooldownUnavailable
from .errors import CommentPostingError
from .models import Comment
from .policies import CommentDeletionMode, comment_deletion_mode
from .ports import CommentMediaError
from .presentation import TopLevelCommentForm, article_comment_context
from .presentation.deletion_forms import CommentDeletionForm
from .queries import (
    CommentCursorError,
    article_comment_access,
    public_reply_page,
)
from .receipts import (
    add_comment_receipt,
    decode_comment_receipts,
    set_comment_receipt_cookie,
)
from .services import create_top_level_comment, stage_top_level_comment_image
from .services.deletion import (
    CommentDeletionError,
    delete_comment_as_admin,
    delete_comment_as_owner,
    delete_own_comment,
)


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _posting_status(code: str) -> int:
    if code in {
        "comments.body_invalid.v1",
        "comments.images_invalid.v1",
    }:
        return 422
    if code == "comments.cooldown_active.v1":
        return 429
    if code in {
        "comments.login_required.v1",
        "comments.account_unavailable.v1",
        "comments.network_restricted.v1",
    }:
        return 403
    if code == "comments.closed.v1":
        return 409
    return 404


def _panel_response(request, article_id: str, context, *, status: int):
    template = (
        "comments/partials/article_panel.html"
        if _is_htmx(request)
        else "comments/article_comment_form_page.html"
    )
    response = render(request, template, context, status=status)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _article_context_or_404(**kwargs):
    try:
        return article_comment_context(**kwargs)
    except (ArticleLoginRequired, ArticleNotFound):
        raise Http404 from None


def _comment_list_error(request, *, status: int = 422):
    response = render(
        request,
        "comments/partials/list_error.html",
        {"comment_list_error": "评论列表未能继续加载，请刷新页面重试。"},
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _requested_deletion_mode(value) -> CommentDeletionMode:
    try:
        return CommentDeletionMode(value)
    except (TypeError, ValueError):
        raise Http404 from None


def _deletion_capability(request, *, article_id: str, comment_id: str):
    try:
        access = article_comment_access(
            actor_id=getattr(request, "account_id", None),
            article_id=article_id,
        )
    except (ArticleLoginRequired, ArticleNotFound):
        raise Http404 from None
    comment = Comment.objects.filter(
        pk=comment_id,
        thread_id=access.thread_id,
    ).first()
    if comment is None:
        raise Http404
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


def _delete_dialog_response(
    request,
    *,
    article_id: str,
    comment: Comment,
    mode: CommentDeletionMode,
    form: CommentDeletionForm,
    status: int = 200,
):
    title = {
        CommentDeletionMode.SELF: "删除自己的评论？",
        CommentDeletionMode.OWNER: "删除这条评论？",
        CommentDeletionMode.ADMIN: "管理员删除这条评论？",
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
            "delete_url": reverse(
                "article:comment-delete",
                kwargs={"article_id": article_id, "comment_id": comment.id},
            ),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    if status == 422:
        response.headers["HX-Retarget"] = "#comment-dialog-host"
        response.headers["HX-Reswap"] = "innerHTML"
    return response


@require_GET
def confirm_article_comment_delete(request, article_id, comment_id):
    comment, mode = _deletion_capability(
        request,
        article_id=article_id,
        comment_id=comment_id,
    )
    if _requested_deletion_mode(request.GET.get("mode")) != mode:
        raise Http404
    return _delete_dialog_response(
        request,
        article_id=article_id,
        comment=comment,
        mode=mode,
        form=CommentDeletionForm(initial={"mode": mode.value}),
    )


@require_POST
def delete_article_comment(request, article_id, comment_id):
    comment, mode = _deletion_capability(
        request,
        article_id=article_id,
        comment_id=comment_id,
    )
    if _requested_deletion_mode(request.POST.get("mode")) != mode:
        raise Http404
    form = CommentDeletionForm(request.POST)
    if not form.is_valid():
        return _delete_dialog_response(
            request,
            article_id=article_id,
            comment=comment,
            mode=mode,
            form=form,
            status=422,
        )
    command = {
        CommentDeletionMode.SELF: delete_own_comment,
        CommentDeletionMode.OWNER: delete_comment_as_owner,
        CommentDeletionMode.ADMIN: delete_comment_as_admin,
    }[mode]
    kwargs = {
        "comment_id": comment.id,
        "actor_id": getattr(request, "account_id", None),
        "client_ip": request.client_ip,
        "trace_code": request.trace_code,
    }
    if mode == CommentDeletionMode.ADMIN:
        kwargs["reason"] = form.cleaned_data["reason"]
    try:
        command(**kwargs)
    except CommentDeletionError as exc:
        if exc.code == "comments.deletion_reason_invalid.v1":
            form.add_error("reason", exc.safe_message)
            return _delete_dialog_response(
                request,
                article_id=article_id,
                comment=comment,
                mode=mode,
                form=form,
                status=422,
            )
        if exc.code == "comments.media_cleanup_failed.v1":
            context = _article_context_or_404(
                request=request,
                article_id=article_id,
            )
            context["comment_system_error"] = exc.safe_message
            context["comment_trace_code"] = request.trace_code
            return _panel_response(request, article_id, context, status=503)
        raise Http404 from None
    if not _is_htmx(request):
        return HttpResponseRedirect(
            f"{reverse('article:detail', kwargs={'article_id': article_id})}#comment-thread"
        )
    return _panel_response(
        request,
        article_id,
        _article_context_or_404(
            request=request,
            article_id=article_id,
            feedback="评论已删除。",
        ),
        status=200,
    )


@require_GET
def article_comment_page(request, article_id):
    cursor = request.GET.get("cursor") or None
    try:
        context = _article_context_or_404(
            request=request,
            article_id=article_id,
            sort=request.GET.get("sort", "earliest"),
            cursor=cursor,
        )
    except CommentCursorError:
        return _comment_list_error(request)
    template = (
        "comments/partials/top_level_batch.html"
        if cursor is not None
        else "comments/partials/public_list.html"
    )
    response = render(request, template, context)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def article_comment_replies(request, article_id, root_id):
    try:
        access = article_comment_access(
            actor_id=getattr(request, "account_id", None),
            article_id=article_id,
        )
        page = public_reply_page(
            thread_id=access.thread_id,
            can_view=access.can_view,
            root_id=root_id,
            cursor=request.GET.get("cursor") or None,
            actor_id=access.actor_id,
            thread_owner_id=access.owner_id,
            is_administrator=access.is_administrator,
        )
    except (ArticleLoginRequired, ArticleNotFound):
        raise Http404 from None
    except CommentCursorError:
        return _comment_list_error(request)
    response = render(
        request,
        "comments/partials/reply_batch.html",
        {
            "reply_page": page,
            "comment_article_id": article_id,
            "comment_root_id": root_id,
            "focus_reply_batch": True,
        },
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_POST
def create_article_comment(request, article_id):
    form = TopLevelCommentForm(request.POST)
    if not form.is_valid():
        return _panel_response(
            request,
            article_id,
            _article_context_or_404(request=request, article_id=article_id, form=form),
            status=422,
        )

    try:
        result = create_top_level_comment(
            target_type="ARTICLE",
            target_id=article_id,
            actor_id=getattr(request, "account_id", None),
            client_ip=request.client_ip,
            body=form.cleaned_data["body"],
            image_refs=form.image_refs,
            trace_code=request.trace_code,
        )
    except CommentCooldownUnavailable:
        context = _article_context_or_404(
            request=request,
            article_id=article_id,
            form=form,
        )
        context["comment_system_error"] = "评论服务暂时不可用，请稍后重试。"
        context["comment_trace_code"] = request.trace_code
        response = _panel_response(request, article_id, context, status=503)
        response.headers["X-Kaj-Inline-Error"] = "true"
        return response
    except CommentPostingError as exc:
        code = getattr(exc, "code", "comments.target_not_found.v1")
        message = getattr(exc, "safe_message", "评论未能提交，请重试。")
        field = getattr(exc, "field", None)
        form.add_error("body" if field == "body" else None, message)
        status = _posting_status(code)
        response = _panel_response(
            request,
            article_id,
            _article_context_or_404(request=request, article_id=article_id, form=form),
            status=status,
        )
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            response.headers["Retry-After"] = str(retry_after)
        return response

    receipts = decode_comment_receipts(
        request.COOKIES.get(settings.COMMENTS_RECEIPT_COOKIE_NAME)
    )
    if getattr(request, "account_id", None) is None:
        receipts = add_comment_receipt(receipts, result.comment_id)
    if not _is_htmx(request):
        response = HttpResponseRedirect(
            f"{reverse('article:detail', kwargs={'article_id': article_id})}#comment-thread"
        )
    else:
        response = _panel_response(
            request,
            article_id,
            _article_context_or_404(
                request=request,
                article_id=article_id,
                feedback="评论已提交，将在 10 分钟后公开。",
                receipt_ids=receipts,
            ),
            status=201,
        )
    if getattr(request, "account_id", None) is None:
        set_comment_receipt_cookie(response, receipts)
    return response


@require_POST
def upload_article_comment_image(request, article_id):
    uploaded = request.FILES.get("file")
    if uploaded is None or len(request.FILES) != 1:
        response = render(
            request,
            "comments/partials/upload_result.html",
            {"upload_error": "请选择一张图片后重试。"},
            status=422,
        )
    else:
        try:
            result = stage_top_level_comment_image(
                target_type="ARTICLE",
                target_id=article_id,
                actor_id=getattr(request, "account_id", None),
                client_ip=request.client_ip,
                original_name=uploaded.name,
                declared_content_type=uploaded.content_type or "",
                chunks=uploaded.chunks(),
            )
        except CommentMediaError as exc:
            response = render(
                request,
                "comments/partials/upload_result.html",
                {
                    "upload_error": getattr(
                        exc, "safe_message", "图片未能上传，请重试。"
                    ),
                    "original_name": uploaded.name,
                },
                status=422,
            )
        except CommentPostingError as exc:
            response = render(
                request,
                "comments/partials/upload_result.html",
                {
                    "upload_error": exc.safe_message,
                    "original_name": uploaded.name,
                },
                status=_posting_status(exc.code),
            )
        else:
            response = render(
                request,
                "comments/partials/upload_result.html",
                {"upload": result},
                status=201,
            )
    response.headers["Cache-Control"] = "private, no-store"
    return response
