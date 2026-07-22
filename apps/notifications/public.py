from apps.notifications.consumers import (
    consume_account_deleted,
    consume_author_role_changed,
)
from apps.notifications.queries import (
    notification_for_recipient,
    notifications_for_recipient,
)
from apps.notifications.services.delivery import (
    NotificationRejected,
    NotificationTemplateSchema,
    deliver_notification,
    register_notification_template,
)

__all__ = [
    "NotificationRejected",
    "NotificationTemplateSchema",
    "deliver_notification",
    "consume_author_role_changed",
    "consume_account_deleted",
    "notification_for_recipient",
    "notifications_for_recipient",
    "register_notification_template",
]
