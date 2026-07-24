from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.content.public import ArticleLoginRequired, ArticleNotFound

from .cooldown import CommentCooldownUnavailable
from .errors import CommentPostingError
from .ports import CommentMediaError
from .presentation import TopLevelCommentForm, article_comment_context
from .receipts import (
    add_comment_receipt,
    decode_comment_receipts,
    set_comment_receipt_cookie,
)
from .services import create_top_level_comment, stage_top_level_comment_image


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
