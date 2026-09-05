from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.accounts.public import is_administrator
from apps.administration.forms.notifications import (
    BroadcastConfirmationForm,
    BroadcastForm,
    BroadcastVisibilityForm,
)
from apps.notifications.public import (
    BroadcastError,
    BroadcastStateError,
    NotificationRejected,
    broadcast_detail,
    broadcast_list,
    create_broadcast,
    delete_broadcast,
    hide_broadcast,
    restore_broadcast,
)
from apps.operations.public import record_audit_entry

_STATE_LABELS = {
    "VISIBLE": "可见",
    "HIDDEN": "已隐藏",
    "DELETED": "已删除",
}
_VISIBILITY_COPY = {
    "hide": {
        "title": "确认隐藏这条群发通知？",
        "description": "隐藏后所有收件人都无法查看；管理员之后可以恢复。",
        "label": "确认隐藏",
    },
    "restore": {
        "title": "确认恢复这条群发通知？",
        "description": "恢复后通知会重新出现在所有原收件人的通知列表中。",
        "label": "确认恢复",
    },
    "delete": {
        "title": "确认删除这条群发通知？",
        "description": "删除后所有收件人都无法查看，产品内不提供恢复入口。",
        "label": "确认删除",
    },
}


def _page(value: str) -> int:
    try:
        page = int(value or "1")
    except ValueError:
        raise ValueError("Invalid recipient page") from None
    if page < 1:
        raise ValueError("Invalid recipient page")
    return page


def _detail(request: HttpRequest, notification_id: str):
    if not notification_id:
        return None
    try:
        return broadcast_detail(
            notification_id=notification_id,
            is_admin=True,
            recipient_state=request.GET.get("recipient_state", ""),
            keyword=request.GET.get("q", ""),
            page=_page(request.GET.get("page", "1")),
        )
    except PermissionError:
        raise Http404 from None


def _allowed_operation(state: str, operation: str) -> bool:
    return (state, operation) in {
        ("VISIBLE", "hide"),
        ("VISIBLE", "delete"),
        ("HIDDEN", "restore"),
        ("HIDDEN", "delete"),
    }


def _render(
    request: HttpRequest,
    *,
    broadcast_form=None,
    broadcast_confirmation=None,
    visibility_form=None,
    visibility_operation="",
    detail_id="",
    status=200,
    query_error="",
) -> HttpResponse:
    selected_id = detail_id or request.GET.get("detail", "")
    try:
        broadcast_page = broadcast_list(
            is_admin=True,
            page=_page(request.GET.get("page", "1")),
            page_size=20,
        )
        detail = _detail(request, selected_id)
    except ValueError:
        broadcast_page = broadcast_list(is_admin=True, page=1, page_size=20)
        detail = None
        query_error = "收件回执筛选或页码无效，请重新选择。"
        status = 422

    confirm_id = request.GET.get("confirm", "")
    operation = request.GET.get("operation", "")
    if visibility_form is not None:
        confirm_id = visibility_form["notification_id"].value() or ""
        operation = visibility_operation
    if confirm_id:
        try:
            confirm_detail = broadcast_detail(
                notification_id=confirm_id,
                is_admin=True,
            )
        except PermissionError:
            raise Http404 from None
        if confirm_detail is None or not _allowed_operation(
            confirm_detail.state, operation
        ):
            raise Http404
        detail = detail or confirm_detail
        selected_id = detail.notification_id
        visibility_form = visibility_form or BroadcastVisibilityForm(
            operation=operation,
            initial={"notification_id": confirm_id, "confirm": operation},
        )

    response = render(
        request,
        "administration/notifications.html",
        {
            "broadcast_rows": broadcast_page.items,
            "broadcast_page": broadcast_page,
            "broadcast_list_pagination_query": urlencode(
                {
                    key: value
                    for key, value in request.GET.items()
                    if key not in {"page", "detail", "recipient_state", "q"}
                }
            ),
            "broadcast_detail": detail,
            "broadcast_form": broadcast_form or BroadcastForm(),
            "broadcast_confirmation": broadcast_confirmation,
            "visibility_form": visibility_form,
            "visibility_operation": operation,
            "visibility_copy": _VISIBILITY_COPY.get(operation),
            "visibility_dialog_id": (
                f"broadcast-visibility-{confirm_id}" if confirm_id else ""
            ),
            "state_labels": _STATE_LABELS,
            "selected_id": selected_id,
            "recipient_state": request.GET.get("recipient_state", ""),
            "recipient_keyword": request.GET.get("q", ""),
            "broadcast_pagination_query": urlencode(
                {key: value for key, value in request.GET.items() if key != "page"}
            ),
            "query_error": query_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _metadata(request: HttpRequest, actor_id):
    return {
        "actor_id": actor_id,
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
        "authorize_administrator": is_administrator,
        "audit_writer": record_audit_entry,
    }


def notifications(request: HttpRequest) -> HttpResponse:
    actor_id = getattr(request, "account_id", None)
    if not is_administrator(actor_id):
        raise PermissionDenied
    if request.method == "GET":
        return _render(request)

    action = request.POST.get("action", "")
    if action == "preview_broadcast":
        form = BroadcastForm(request.POST)
        if not form.is_valid():
            return _render(request, broadcast_form=form, status=422)
        confirmation = BroadcastConfirmationForm(
            initial={
                "headline": form.cleaned_data["headline"],
                "message": form.cleaned_data["message"],
                "confirm": "broadcast",
            }
        )
        return _render(
            request,
            broadcast_form=form,
            broadcast_confirmation=confirmation,
        )

    if action == "broadcast":
        form = BroadcastConfirmationForm(request.POST)
        if not form.is_valid():
            visible_form = BroadcastForm(request.POST)
            visible_form.is_valid()
            visible_form.add_error(None, "通知确认数据无效，请重新填写。")
            return _render(
                request,
                broadcast_form=visible_form,
                status=422,
            )
        try:
            notification = create_broadcast(
                headline=form.cleaned_data["headline"],
                message=form.cleaned_data["message"],
                **_metadata(request, actor_id),
            )
        except (BroadcastError, NotificationRejected):
            form.add_error(None, "通知内容无法安全发送，请检查后重试。")
            return _render(
                request,
                broadcast_form=BroadcastForm(request.POST),
                broadcast_confirmation=form,
                status=422,
            )
        return redirect(
            f"{reverse('admin:notifications')}?saved=broadcast&detail={notification.id}"
        )

    if action in {"hide", "restore", "delete"}:
        form = BroadcastVisibilityForm(request.POST, operation=action)
        if not form.is_valid():
            return _render(
                request,
                visibility_form=form,
                visibility_operation=action,
                detail_id=request.POST.get("notification_id", ""),
                status=422,
            )
        command = {
            "hide": hide_broadcast,
            "restore": restore_broadcast,
            "delete": delete_broadcast,
        }[action]
        try:
            notification = command(
                notification_id=form.cleaned_data["notification_id"],
                **_metadata(request, actor_id),
            )
        except PermissionError:
            raise Http404 from None
        except BroadcastStateError:
            form.add_error(None, "通知状态已经变化，请关闭确认框后重新查看。")
            return _render(
                request,
                visibility_form=form,
                visibility_operation=action,
                detail_id=form.cleaned_data["notification_id"],
                status=409,
            )
        return redirect(
            f"{reverse('admin:notifications')}?saved={action}&detail={notification.id}"
        )

    form = BroadcastForm(request.POST)
    form.add_error(None, "请选择有效的通知操作。")
    return _render(request, broadcast_form=form, status=422)
