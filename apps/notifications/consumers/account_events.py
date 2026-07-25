from uuid import UUID

from apps.core.events import EventEnvelope, consume_once
from apps.core.ids import is_ulid
from apps.core.time.clock import Clock
from apps.notifications.models import Notification
from apps.notifications.services.delivery import (
    deliver_notification,
)
from apps.notifications.services.recipients import notification_recipient_exists
from apps.notifications.templates_registry import register_builtin_templates

AUTHOR_ROLE_CHANGED_EVENT = "account.author_role_changed.v1"
AUTHOR_ROLE_CHANGED_CONSUMER = "notifications.account_author_role_changed.v1"
ACCOUNT_DELETED_EVENT = "account.deleted.v1"
ACCOUNT_DELETED_CONSUMER = "notifications.account_deleted.v1"


def register_account_event_templates() -> None:
    register_builtin_templates(keys=(AUTHOR_ROLE_CHANGED_EVENT,))


def _deliver_author_role_changed(envelope: EventEnvelope) -> None:
    if (
        envelope.event_type != AUTHOR_ROLE_CHANGED_EVENT
        or envelope.schema_version != 1
        or envelope.aggregate_type != "account"
        or set(envelope.payload) != {"enabled"}
        or not isinstance(envelope.payload["enabled"], bool)
    ):
        raise ValueError("Unsupported account role event")
    try:
        recipient_id = UUID(envelope.aggregate_id)
    except ValueError:
        raise ValueError("Invalid account role event target") from None
    if not notification_recipient_exists(recipient_id):
        return
    deliver_notification(
        template_key=AUTHOR_ROLE_CHANGED_EVENT,
        recipient_ids=(recipient_id,),
        target_id=envelope.aggregate_id,
        payload={"enabled": envelope.payload["enabled"]},
        actor_id=envelope.actor_id,
        dedupe_key=f"account-role:{envelope.event_id}",
    )


def consume_author_role_changed(
    envelope: EventEnvelope,
    *,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    return consume_once(
        envelope,
        AUTHOR_ROLE_CHANGED_CONSUMER,
        _deliver_author_role_changed,
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=clock,
    )


def _remove_deleted_account_notifications(envelope: EventEnvelope) -> None:
    if (
        envelope.event_type != ACCOUNT_DELETED_EVENT
        or envelope.schema_version != 1
        or envelope.aggregate_type != "account"
        or set(envelope.payload)
        != {
            "deletion_id",
            "was_author",
            "author_disposition",
            "disposition_id",
            "article_count",
        }
        or not isinstance(envelope.payload["deletion_id"], str)
        or not is_ulid(envelope.payload["deletion_id"])
    ):
        raise ValueError("Unsupported account deletion event")
    try:
        UUID(envelope.aggregate_id)
    except ValueError:
        raise ValueError("Invalid account deletion event target") from None
    Notification.objects.filter(receipts__isnull=True).delete()


def consume_account_deleted(
    envelope: EventEnvelope,
    *,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    return consume_once(
        envelope,
        ACCOUNT_DELETED_CONSUMER,
        _remove_deleted_account_notifications,
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=clock,
    )
