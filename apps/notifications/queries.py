from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.notifications.models import NotificationReceipt


@dataclass(frozen=True, slots=True)
class RecipientNotification:
    notification_id: str
    template_key: str
    actor_id: str | None
    target_type: str
    target_id: str
    payload_safe: dict[str, object]
    read_at: datetime | None
    created_at: datetime


def notifications_for_recipient(
    *, recipient_id: UUID | str, limit: int = 100
) -> list[RecipientNotification]:
    if not 1 <= limit <= 200:
        raise ValueError("Invalid notification query limit")
    rows = (
        NotificationReceipt.objects.select_related("notification")
        .filter(
            recipient_id=recipient_id,
            notification__hidden_at__isnull=True,
            notification__deleted_at__isnull=True,
        )
        .order_by("-notification__created_at", "-notification_id")[:limit]
    )
    return [
        RecipientNotification(
            notification_id=row.notification_id,
            template_key=row.notification.template_key,
            actor_id=(
                str(row.notification.actor_id) if row.notification.actor_id else None
            ),
            target_type=row.notification.target_type,
            target_id=row.notification.target_id,
            payload_safe=row.notification.payload_safe,
            read_at=row.read_at,
            created_at=row.notification.created_at,
        )
        for row in rows
    ]


def notification_for_recipient(
    *, notification_id: str, recipient_id: UUID | str
) -> RecipientNotification:
    row = (
        NotificationReceipt.objects.select_related("notification")
        .filter(
            notification_id=notification_id,
            recipient_id=recipient_id,
            notification__hidden_at__isnull=True,
            notification__deleted_at__isnull=True,
        )
        .first()
    )
    if row is None:
        raise PermissionError("Notification access denied")
    return RecipientNotification(
        notification_id=row.notification_id,
        template_key=row.notification.template_key,
        actor_id=(
            str(row.notification.actor_id) if row.notification.actor_id else None
        ),
        target_type=row.notification.target_type,
        target_id=row.notification.target_id,
        payload_safe=row.notification.payload_safe,
        read_at=row.read_at,
        created_at=row.notification.created_at,
    )
