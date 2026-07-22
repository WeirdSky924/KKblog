from uuid import UUID

from apps.notifications.models import NotificationReceipt


def notification_recipient_exists(account_id: UUID) -> bool:
    """Check the model behind this owner's recipient relation without importing it."""

    recipient_field = NotificationReceipt._meta.get_field("recipient")
    recipient_model = recipient_field.remote_field.model
    return recipient_model._base_manager.filter(pk=account_id).exists()
