from collections.abc import Callable
from uuid import UUID

from django.db import connection, transaction

from apps.core.ids import new_ulid
from apps.notifications.models import NotificationReceipt
from apps.notifications.services.delivery import (
    NOTIFICATION_MARKDOWN_MAX_LENGTH,
    deliver_notification,
)

LEGACY_BROADCAST_TEMPLATE_KEY = "admin.broadcast.v1"
BROADCAST_TEMPLATE_KEY = "admin.broadcast.v2"
BROADCAST_TEMPLATE_KEYS = frozenset(
    {LEGACY_BROADCAST_TEMPLATE_KEY, BROADCAST_TEMPLATE_KEY}
)
BROADCAST_MESSAGE_MAX_LENGTH = NOTIFICATION_MARKDOWN_MAX_LENGTH

AdministratorAuthorizer = Callable[[UUID], bool]
AuditWriter = Callable[..., object]


class BroadcastError(ValueError):
    pass


def normalize_broadcast_message_markdown(value: object) -> str:
    if not isinstance(value, str):
        raise BroadcastError("Broadcast message must be Markdown text")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > BROADCAST_MESSAGE_MAX_LENGTH
        or "\x00" in normalized
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in normalized
        )
    ):
        raise BroadcastError("Broadcast message Markdown is invalid")
    return normalized


def _actor_id(value: UUID | str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise PermissionError("Broadcast access denied") from None


def _require_administrator(
    actor_id: UUID, authorize_administrator: AdministratorAuthorizer
) -> None:
    if not callable(authorize_administrator) or not authorize_administrator(actor_id):
        raise PermissionError("Broadcast access denied")


def _registered_recipient_ids() -> tuple[UUID, ...]:
    recipient_field = NotificationReceipt._meta.get_field("recipient")
    account_model = recipient_field.remote_field.model
    if connection.vendor != "postgresql":
        raise BroadcastError("Broadcast requires PostgreSQL")
    table = connection.ops.quote_name(account_model._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f"LOCK TABLE {table} IN SHARE MODE")
    return tuple(
        account_model._base_manager.order_by("pk").values_list("pk", flat=True)
    )


def create_broadcast(
    *,
    headline: str,
    message: str,
    actor_id: UUID | str,
    trace_code: str,
    client_ip: str,
    authorize_administrator: AdministratorAuthorizer,
    audit_writer: AuditWriter,
):
    actor = _actor_id(actor_id)
    if not callable(audit_writer):
        raise TypeError("Broadcast audit writer must be callable")
    message_markdown = normalize_broadcast_message_markdown(message)
    payload = {"headline": headline, "message_markdown": message_markdown}
    with transaction.atomic():
        _require_administrator(actor, authorize_administrator)
        from apps.notifications.templates_registry import render_notification

        render_notification(BROADCAST_TEMPLATE_KEY, payload)
        recipients = _registered_recipient_ids()
        if not recipients:
            raise BroadcastError("Broadcast requires registered recipients")
        notification = deliver_notification(
            template_key=BROADCAST_TEMPLATE_KEY,
            recipient_ids=recipients,
            target_id=new_ulid(),
            payload=payload,
            actor_id=actor,
        )
        audit_writer(
            action="notifications.broadcast.create",
            actor_id=actor,
            target_id=notification.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={},
            after={"state": "VISIBLE", "recipient_count": len(recipients)},
            summary="管理员创建全体站内通知",
        )
        return notification
