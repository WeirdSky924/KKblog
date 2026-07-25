from uuid import UUID

from apps.notifications.models import NotificationReceipt


def existing_notification_recipient_ids(
    account_ids: tuple[UUID, ...],
) -> tuple[UUID, ...]:
    """Return existing recipients in caller order via this owner's relation."""

    if any(not isinstance(account_id, UUID) for account_id in account_ids):
        raise TypeError("Notification recipient IDs must be UUID values")
    unique_ids = tuple(dict.fromkeys(account_ids))
    if not unique_ids:
        return ()
    recipient_field = NotificationReceipt._meta.get_field("recipient")
    recipient_model = recipient_field.remote_field.model
    existing = set(
        recipient_model._base_manager.filter(pk__in=unique_ids).values_list(
            "pk", flat=True
        )
    )
    return tuple(account_id for account_id in unique_ids if account_id in existing)


def notification_recipient_exists(account_id: UUID) -> bool:
    """Check the model behind this owner's recipient relation without importing it."""

    return bool(existing_notification_recipient_ids((account_id,)))
