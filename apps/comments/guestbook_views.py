from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.core.errors.codes import ErrorCode, spec_for
from apps.core.errors.handlers import render_error_response

from .cooldown import CommentCooldownUnavailable
from .errors import CommentPostingError
from .http import is_htmx, posting_status
from .ports import CommentMediaError
from .presentation import TopLevelCommentForm, guestbook_comment_context
from .queries import CommentCursorError
from .receipts import (
    add_comment_receipt,
    decode_comment_receipts,
    set_comment_receipt_cookie,
)
from .services import (
    GuestbookUnavailableError,
    create_top_level_comment,
    stage_top_level_comment_image,
)


def _unavailable(request):
    return render_error_response(request, spec_for(ErrorCode.SERVICE_UNAVAILABLE))


def _panel_response(request, context, *, status: int):
    template = (
        "comments/partials/thread_panel.html"
        if is_htmx(request)
        else "comments/thread_page.html"
    )
    response = render(request, template, context, status=status)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _list_error(request):
    response = render(
        request,
        "comments/partials/list_error.html",
        {"comment_list_error": "留言列表未能继续加载，请刷新页面重试。"},
        status=422,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def guestbook_page(request):
    try:
        context = guestbook_comment_context(request=request)
    except GuestbookUnavailableError:
        return _unavailable(request)
    response = render(request, "comments/thread_page.html", context)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def guestbook_comment_page(request):
    cursor = request.GET.get("cursor") or None
    try:
        context = guestbook_comment_context(
            request=request,
            sort=request.GET.get("sort", "earliest"),
            cursor=cursor,
        )
    except GuestbookUnavailableError:
        return _unavailable(request)
    except CommentCursorError:
        return _list_error(request)
    template = (
        "comments/partials/top_level_batch.html"
        if cursor is not None
        else "comments/partials/public_list.html"
    )
    response = render(request, template, context)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_POST
def create_guestbook_comment(request):
    form = TopLevelCommentForm(request.POST, noun="留言")
    if not form.is_valid():
        try:
            context = guestbook_comment_context(request=request, form=form)
        except GuestbookUnavailableError:
            return _unavailable(request)
        return _panel_response(request, context, status=422)
    try:
        result = create_top_level_comment(
            target_type="GUESTBOOK",
            target_id="site",
            actor_id=getattr(request, "account_id", None),
            client_ip=request.client_ip,
            body=form.cleaned_data["body"],
            image_refs=form.image_refs,
            trace_code=request.trace_code,
        )
    except GuestbookUnavailableError:
        return _unavailable(request)
    except CommentCooldownUnavailable:
        context = guestbook_comment_context(request=request, form=form)
        context["comment_system_error"] = "留言服务暂时不可用，请稍后重试。"
        context["comment_trace_code"] = request.trace_code
        response = _panel_response(request, context, status=503)
        response.headers["X-Kaj-Inline-Error"] = "true"
        return response
    except CommentPostingError as exc:
        form.add_error("body" if exc.field == "body" else None, exc.safe_message)
        try:
            context = guestbook_comment_context(request=request, form=form)
        except GuestbookUnavailableError:
            return _unavailable(request)
        response = _panel_response(request, context, status=posting_status(exc.code))
        if exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    receipts = decode_comment_receipts(
        request.COOKIES.get(settings.COMMENTS_RECEIPT_COOKIE_NAME)
    )
    if getattr(request, "account_id", None) is None:
        receipts = add_comment_receipt(receipts, result.comment_id)
    if not is_htmx(request):
        response = HttpResponseRedirect(f"{reverse('public:guestbook')}#comment-thread")
    else:
        response = _panel_response(
            request,
            guestbook_comment_context(
                request=request,
                feedback="留言已提交，将在 10 分钟后公开。",
                receipt_ids=receipts,
            ),
            status=201,
        )
    if getattr(request, "account_id", None) is None:
        set_comment_receipt_cookie(response, receipts)
    return response


@require_POST
def upload_guestbook_comment_image(request):
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
                target_type="GUESTBOOK",
                target_id="site",
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
                {"upload_error": exc.safe_message, "original_name": uploaded.name},
                status=422,
            )
        except CommentPostingError as exc:
            response = render(
                request,
                "comments/partials/upload_result.html",
                {"upload_error": exc.safe_message, "original_name": uploaded.name},
                status=posting_status(exc.code),
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
