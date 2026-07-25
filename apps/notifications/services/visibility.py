from uuid import UUID

from django.db import transaction

from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.notifications.models import Notification
from apps.notifications.services.broadcast import (
    BROADCAST_TEMPLATE_KEY,
    AdministratorAuthorizer,
    AuditWriter,
    _actor_id,
    _require_administrator,
)


class BroadcastStateError(ValueError):
    pass


def _state(notification: Notification) -> str:
    if notification.deleted_at is not None:
        return "DELETED"
    if notification.hidden_at is not None:
        return "HIDDEN"
    return "VISIBLE"


def _notification_id(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise PermissionError("Broadcast access denied") from None


def _change_visibility(
    *,
    notification_id: str,
    action: str,
    actor_id: UUID | str,
    trace_code: str,
    client_ip: str,
    authorize_administrator: AdministratorAuthorizer,
    audit_writer: AuditWriter,
    clock: Clock | None = None,
) -> Notification:
    actor = _actor_id(actor_id)
    normalized_id = _notification_id(notification_id)
    if action not in {"hide", "restore", "delete"}:
        raise BroadcastStateError("Invalid broadcast visibility action")
    if not callable(audit_writer):
        raise TypeError("Broadcast audit writer must be callable")
    with transaction.atomic():
        _require_administrator(actor, authorize_administrator)
        notification = (
            Notification.objects.select_for_update()
            .filter(pk=normalized_id, template_key=BROADCAST_TEMPLATE_KEY)
            .first()
        )
        if notification is None:
            raise PermissionError("Broadcast access denied")
        before = _state(notification)
        if before == "DELETED":
            if action == "delete":
                return notification
            raise BroadcastStateError("Deleted broadcasts cannot change visibility")
        if action == "hide":
            if before == "HIDDEN":
                return notification
            notification.hidden_at = (clock or SystemClock()).now()
            update_fields = ("hidden_at",)
        elif action == "restore":
            if before == "VISIBLE":
                return notification
            notification.hidden_at = None
            update_fields = ("hidden_at",)
        else:
            notification.deleted_at = (clock or SystemClock()).now()
            update_fields = ("deleted_at",)
        notification.save(update_fields=update_fields)
        after = _state(notification)
        audit_writer(
            action=f"notifications.broadcast.{action}",
            actor_id=actor,
            target_id=notification.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"state": before},
            after={"state": after},
            summary=f"管理员更新全体站内通知状态：{after}",
        )
        return notification


def hide_broadcast(**kwargs) -> Notification:
    return _change_visibility(action="hide", **kwargs)


def restore_broadcast(**kwargs) -> Notification:
    return _change_visibility(action="restore", **kwargs)


def delete_broadcast(**kwargs) -> Notification:
    return _change_visibility(action="delete", **kwargs)
