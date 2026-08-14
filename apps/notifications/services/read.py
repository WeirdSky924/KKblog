from uuid import UUID

from django.db import transaction

from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.notifications.models import NotificationReceipt


def _recipient_id(value: UUID | str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise PermissionError("Notification access denied") from None


def mark_notification_read(
    *,
    recipient_id: UUID | str,
    notification_id: str,
    clock: Clock | None = None,
) -> bool:
    identity = _recipient_id(recipient_id)
    try:
        normalized_id = normalize_ulid(notification_id)
    except (TypeError, ValueError):
        raise PermissionError("Notification access denied") from None
    active_clock = clock or SystemClock()
    with transaction.atomic():
        receipt = (
            NotificationReceipt.objects.select_for_update()
            .filter(
                recipient_id=identity,
                notification_id=normalized_id,
                notification__hidden_at__isnull=True,
                notification__deleted_at__isnull=True,
            )
            .first()
        )
        if receipt is None:
            raise PermissionError("Notification access denied")
        if receipt.read_at is not None:
            return False
        receipt.read_at = active_clock.now()
        receipt.save(update_fields=("read_at",))
        return True


def mark_all_notifications_read(
    *, recipient_id: UUID | str, clock: Clock | None = None
) -> int:
    identity = _recipient_id(recipient_id)
    now = (clock or SystemClock()).now()
    with transaction.atomic():
        receipt_ids = tuple(
            NotificationReceipt.objects.select_for_update()
            .filter(
                recipient_id=identity,
                read_at__isnull=True,
                notification__hidden_at__isnull=True,
                notification__deleted_at__isnull=True,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        if not receipt_ids:
            return 0
        return NotificationReceipt.objects.filter(
            id__in=receipt_ids,
            read_at__isnull=True,
        ).update(read_at=now)


def mark_target_notifications_read(
    *, recipient_id: UUID | str, target_type: str, clock: Clock | None = None
) -> int:
    identity = _recipient_id(recipient_id)
    if (
        not isinstance(target_type, str)
        or not target_type
        or len(target_type) > 64
        or not target_type.replace("_", "").isalnum()
    ):
        raise ValueError("Invalid notification target type")
    now = (clock or SystemClock()).now()
    with transaction.atomic():
        receipt_ids = tuple(
            NotificationReceipt.objects.select_for_update()
            .filter(
                recipient_id=identity,
                read_at__isnull=True,
                notification__target_type=target_type,
                notification__hidden_at__isnull=True,
                notification__deleted_at__isnull=True,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        if not receipt_ids:
            return 0
        return NotificationReceipt.objects.filter(
            id__in=receipt_ids,
            read_at__isnull=True,
        ).update(read_at=now)
