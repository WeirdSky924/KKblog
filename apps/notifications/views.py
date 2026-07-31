import json
import logging
from dataclasses import replace
from urllib.parse import urlencode

from django.db import DatabaseError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.core.http import is_htmx_fragment_request
from apps.notifications.queries import (
    NotificationCursorError,
    notification_detail,
    notification_inbox,
    notification_popover,
    unread_notification_count,
)
from apps.notifications.services.delivery import NotificationRejected
from apps.notifications.services.read import (
    mark_all_notifications_read,
    mark_notification_read,
)

logger = logging.getLogger("kaj.notifications")


def _login_url(next_path: str) -> str:
    return f"{reverse('accounts:login')}?{urlencode({'next': next_path})}"


def _login_required(request, *, next_path: str):
    location = _login_url(next_path)
    if is_htmx_fragment_request(request):
        response = HttpResponse(status=204)
        response.headers["HX-Redirect"] = location
    else:
        response = redirect(location)
    return _no_store(response)


def _no_store(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _trigger(*, notification_id: str | None, unread_count: int) -> str:
    detail = {"unreadCount": unread_count}
    if notification_id is not None:
        detail["notificationId"] = notification_id
    return json.dumps(
        {"kaj:notification-read": detail},
        ensure_ascii=True,
        separators=(",", ":"),
    )


@require_GET
def popover(request):
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return _login_required(request, next_path=reverse("notifications:list"))
    try:
        result = notification_popover(recipient_id=actor_id)
    except (DatabaseError, NotificationRejected):
        logger.error(
            "Notification popover unavailable",
            extra={"trace_code": getattr(request, "trace_code", "-")},
        )
        return _no_store(
            render(
                request,
                "notifications/partials/popover_error.html",
                {"trace_code": getattr(request, "trace_code", "-")},
                status=200,
            )
        )
    return _no_store(
        render(
            request,
            "notifications/partials/popover.html",
            {"notification_popover": result},
        )
    )


@require_GET
def inbox(request):
    actor_id = getattr(request, "account_id", None)
    inbox_url = reverse("notifications:list")
    if actor_id is None:
        return _login_required(request, next_path=inbox_url)
    cursor = request.GET.get("cursor") or None
    error = ""
    status = 200
    try:
        page = notification_inbox(recipient_id=actor_id, cursor=cursor)
    except NotificationCursorError:
        page = notification_inbox(recipient_id=actor_id)
        error = "通知页码已失效，请从最新通知重新查看。"
        status = 422
    context = {
        "notification_page": page,
        "notification_cursor_error": error,
        "notification_unread_count": unread_notification_count(recipient_id=actor_id),
        "notification_all_read": request.GET.get("read") == "all",
        "notification_append": is_htmx_fragment_request(request)
        and cursor is not None
        and not error,
    }
    template = (
        "notifications/partials/inbox_page.html"
        if is_htmx_fragment_request(request) and cursor is not None and not error
        else "notifications/list.html"
    )
    return _no_store(render(request, template, context, status=status))


@require_POST
def open_notification(request, notification_id: str):
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return _login_required(request, next_path=reverse("notifications:list"))
    try:
        item = notification_detail(
            recipient_id=actor_id,
            notification_id=notification_id,
        )
        mark_notification_read(
            recipient_id=actor_id,
            notification_id=notification_id,
        )
    except PermissionError:
        raise Http404 from None
    item = replace(item, is_read=True)
    if not is_htmx_fragment_request(request):
        return _no_store(redirect(reverse("notifications:list")))
    response = render(
        request,
        "notifications/partials/overlay.html",
        {"notification_item": item},
    )
    response.headers["HX-Trigger"] = _trigger(
        notification_id=item.notification_id,
        unread_count=unread_notification_count(recipient_id=actor_id),
    )
    return _no_store(response)


@require_POST
def mark_all_read(request):
    actor_id = getattr(request, "account_id", None)
    inbox_url = reverse("notifications:list")
    if actor_id is None:
        return _login_required(request, next_path=inbox_url)
    mark_all_notifications_read(recipient_id=actor_id)
    if not is_htmx_fragment_request(request):
        return _no_store(redirect(f"{inbox_url}?read=all"))
    response = render(
        request,
        "notifications/partials/inbox_page.html",
        {
            "notification_page": notification_inbox(recipient_id=actor_id),
            "notification_unread_count": 0,
            "notification_all_read": True,
            "notification_cursor_error": "",
            "notification_append": False,
        },
    )
    response.headers["HX-Trigger"] = _trigger(
        notification_id=None,
        unread_count=0,
    )
    return _no_store(response)
