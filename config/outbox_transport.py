from collections.abc import Callable
from dataclasses import dataclass

from apps.content.consumers.account_status import consume_account_status_event
from apps.core.events import ConsumerOutcome, EventEnvelope
from apps.discovery.cache.invalidation import consume_discovery_cache_event
from apps.moderation.consumers.account_deletion import (
    consume_account_deleted as consume_moderation_account_deleted,
)
from apps.notifications.public import (
    consume_account_deleted,
    consume_author_role_changed,
    consume_domain_notification,
)

EventConsumer = Callable[[EventEnvelope], object]


class UnsupportedApplicationEvent(ValueError):
    pass


class ApplicationEventConsumerBusy(RuntimeError):
    pass


_DOMAIN_NOTIFICATION_EVENTS = frozenset(
    {
        "tag.reviewed.v1",
        "tag.restore_conflict.v1",
        "article.admin_viewed.v1",
        "comment.deep_thread.v1",
        "comment.deleted.v1",
        "report.reviewed.v1",
        "report.finalized.v1",
        "report.closed.v1",
        "article.moderated.v1",
        "article.moderation_restored.v1",
        "article.moderation_finalized.v1",
    }
)
_DISCOVERY_EVENTS = frozenset(
    {
        "section.changed.v1",
        "tag.changed.v1",
        "article.published.v1",
        "article.visibility_changed.v1",
        "article.deleted.v1",
        "article.restored.v1",
        "article.purge_requested.v1",
        "article.author_mask_changed.v1",
    }
)
_TERMINAL_EVENTS = frozenset(
    {
        "article.scheduled.v1",
        "article.schedule_cancelled.v1",
        "comment.created.v1",
    }
)


def _routes(event_type: str) -> tuple[EventConsumer, ...]:
    if event_type == "account.author_role_changed.v1":
        return (consume_author_role_changed,)
    if event_type in {"account.disabled.v1", "account.enabled.v1"}:
        return (consume_account_status_event,)
    if event_type == "account.deleted.v1":
        return (consume_moderation_account_deleted, consume_account_deleted)
    if event_type in _DISCOVERY_EVENTS:
        return (consume_discovery_cache_event,)
    if event_type in _DOMAIN_NOTIFICATION_EVENTS:
        return (consume_domain_notification,)
    if event_type in _TERMINAL_EVENTS:
        return ()
    raise UnsupportedApplicationEvent("Application event has no registered route")


@dataclass(frozen=True, slots=True)
class ApplicationEventTransport:
    def publish(self, envelope: EventEnvelope) -> None:
        if not isinstance(envelope, EventEnvelope):
            raise TypeError("Application transport requires an EventEnvelope")
        for consumer in _routes(envelope.event_type):
            result = consumer(envelope)
            if getattr(result, "outcome", None) == ConsumerOutcome.BUSY:
                raise ApplicationEventConsumerBusy(
                    "Application event consumer is not ready"
                )


def build_application_event_transport() -> ApplicationEventTransport:
    return ApplicationEventTransport()
