from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.comments.public import (
    CommentDeletionError,
    GuestbookAdminQueryError,
    GuestbookModerationError,
    GuestbookSettingsError,
    admin_comment_detail,
    delete_comment_as_admin,
    guestbook_admin_page,
    moderate_guestbook_comment,
    update_guestbook_quotas,
)

from ..forms.moderation import (
    CommentDeletionConfirmationForm,
    GuestbookModerationForm,
    GuestbookQuotaForm,
)


def _page(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _detail(request: HttpRequest, comment_id: str):
    try:
        detail = admin_comment_detail(
            actor_id=request.account_id,
            comment_id=comment_id,
        )
    except (LookupError, PermissionError):
        raise Http404 from None
    if detail.target_type != "GUESTBOOK" or detail.target_id != "site":
        raise Http404
    return detail


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    page_error: str = "",
    delete_detail=None,
    delete_form=None,
    quota_form: GuestbookQuotaForm | None = None,
) -> HttpResponse:
    try:
        page = guestbook_admin_page(
            actor_id=request.account_id,
            page=_page(request.GET.get("page")),
            page_size=20,
        )
    except PermissionError:
        raise PermissionDenied from None
    except GuestbookAdminQueryError as exc:
        page_error = str(exc)
        status = 422
        page = None
    if page is not None and quota_form is None:
        quota_form = GuestbookQuotaForm(
            initial={
                "account_daily_limit": page.account_daily_limit,
                "board_daily_limit": page.board_daily_limit,
                "expected_version": page.quota_version,
            }
        )
    response = render(
        request,
        "administration/guestbook.html",
        {
            "guestbook_page": page,
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "delete_detail": delete_detail,
            "delete_form": delete_form,
            "quota_form": quota_form,
            "delete_return_url": f"{reverse('admin:guestbook')}#guestbook-list",
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _post(request: HttpRequest) -> HttpResponse:
    action = request.POST.get("action", "")
    if action == "guestbook_quota_update":
        form = GuestbookQuotaForm(request.POST)
        if not form.is_valid():
            return _render(
                request,
                status=422,
                page_error="请修正每日留言额度后重试。",
                quota_form=form,
            )
        try:
            update_guestbook_quotas(
                actor_id=request.account_id,
                account_daily_limit=form.cleaned_data["account_daily_limit"],
                board_daily_limit=form.cleaned_data["board_daily_limit"],
                expected_version=form.cleaned_data["expected_version"],
                client_ip=request.client_ip,
                trace_code=getattr(request, "trace_code", ""),
            )
        except GuestbookSettingsError as exc:
            is_conflict = "conflict" in exc.code
            return _render(
                request,
                status=409 if is_conflict else 422,
                page_error=exc.safe_message,
                quota_form=None if is_conflict else form,
            )
        return redirect(f"{reverse('admin:guestbook')}?saved=quotas#guestbook-limits")
    if action == "guestbook_moderate":
        form = GuestbookModerationForm(request.POST)
        if not form.is_valid():
            return _render(request, status=422, page_error="留言板操作参数无效。")
        try:
            moderate_guestbook_comment(
                actor_id=request.account_id,
                comment_id=form.cleaned_data["comment_id"],
                operation=form.cleaned_data["operation"],
                flag=form.cleaned_data["flag"],
                client_ip=request.client_ip,
                trace_code=getattr(request, "trace_code", ""),
            )
        except GuestbookModerationError as exc:
            return _render(request, status=422, page_error=exc.safe_message)
        return redirect(f"{reverse('admin:guestbook')}?saved=moderated#guestbook-list")
    if action == "guestbook_delete":
        form = CommentDeletionConfirmationForm(request.POST)
        if not form.is_valid():
            try:
                detail = _detail(request, request.POST.get("comment_id", ""))
            except Http404:
                return _render(request, status=422, page_error="请重新确认留言删除。")
            return _render(
                request,
                status=422,
                page_error="请填写有效的删除确认信息。",
                delete_detail=detail,
                delete_form=form,
            )
        try:
            delete_comment_as_admin(
                actor_id=request.account_id,
                comment_id=form.cleaned_data["comment_id"],
                reason=form.cleaned_data["reason"],
                client_ip=request.client_ip,
                trace_code=getattr(request, "trace_code", ""),
                expected_target_type="GUESTBOOK",
                expected_target_id="site",
            )
        except (CommentDeletionError, PermissionError) as exc:
            safe_message = getattr(exc, "safe_message", "留言删除失败，请稍后重试。")
            return _render(request, status=422, page_error=safe_message)
        return redirect(f"{reverse('admin:guestbook')}?saved=deleted#guestbook-list")
    return _render(request, status=422, page_error="留言板操作无效。")


def guestbook(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "POST":
        return _post(request)
    confirm_id = request.GET.get("confirm", "")
    if confirm_id:
        detail = _detail(request, confirm_id)
        return _render(
            request,
            delete_detail=detail,
            delete_form=CommentDeletionConfirmationForm(
                initial={"comment_id": detail.id, "confirm": "comment_delete"}
            ),
        )
    return _render(request)


__all__ = ["guestbook"]
