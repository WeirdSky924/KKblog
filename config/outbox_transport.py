from collections.abc import Callable
from dataclasses import dataclass

from apps.accounts.public import active_administrator_id
from apps.content.consumers.account_status import consume_account_status_event
from apps.core.events import ConsumerOutcome, EventEnvelope
from apps.discovery.cache.invalidation import consume_discovery_cache_event
from apps.exchange.public import consume_export_task_final_failure
from apps.moderation.consumers.account_deletion import (
    consume_account_deleted as consume_moderation_account_deleted,
)
from apps.navigation.consumers import consume_navigation_section_event
from apps.notifications.public import (
    consume_account_deleted,
    consume_author_role_changed,
    consume_domain_notification,
    consume_operational_state_notification,
    consume_opportunity_notification,
    consume_task_final_failure_notification,
)
from apps.operations.public import (
    consume_backup_task_final_failure,
    consume_task_final_failure_alert,
)

EventConsumer = Callable[[EventEnvelope], object]


class UnsupportedApplicationEvent(ValueError):
    pass


class ApplicationEventConsumerBusy(RuntimeError):
    pass


_ARTICLE_MODERATION_EVENTS = frozenset(
    {
        "article.moderated.v1",
        "article.moderation_restored.v1",
        "article.moderation_finalized.v1",
    }
)
_LEARNING_NOTIFICATION_EVENTS = frozenset(
    {
        "learning.review_approved.v1",
        "learning.review_rejected.v1",
        "learning.review_failed.v1",
        "learning.generation_completed.v1",
        "learning.generation_partial.v1",
        "learning.generation_failed.v1",
        "learning.appeal_approved.v1",
        "learning.appeal_rejected.v1",
    }
)
_DOMAIN_NOTIFICATION_EVENTS = (
    frozenset(
        {
            "tag.reviewed.v1",
            "tag.restore_conflict.v1",
            "article.admin_viewed.v1",
            "comment.deep_thread.v1",
            "comment.deleted.v1",
            "report.reviewed.v1",
            "report.reviewed.v2",
            "report.finalized.v1",
            "report.finalized.v2",
            "report.closed.v1",
            "exchange.import_title_warning.v1",
            "exchange.export_completed.v1",
            "exchange.export_author_content.v1",
        }
    )
    | _ARTICLE_MODERATION_EVENTS
    | _LEARNING_NOTIFICATION_EVENTS
)
_DISCOVERY_EVENTS = (
    frozenset(
        {
            "section.changed.v1",
            "tag.changed.v1",
            "article.published.v1",
            "article.visibility_changed.v1",
            "article.hidden.v1",
            "article.deleted.v1",
            "article.restored.v1",
            "article.purge_requested.v1",
            "article.author_mask_changed.v1",
        }
    )
    | _ARTICLE_MODERATION_EVENTS
)
_TERMINAL_EVENTS = frozenset(
    {
        "article.scheduled.v1",
        "article.schedule_cancelled.v1",
        "comment.created.v1",
        "navigation.changed.v1",
    }
)


def _consume_task_final_failure_notification(envelope: EventEnvelope):
    return consume_task_final_failure_notification(
        envelope,
        administrator_id_provider=active_administrator_id,
    )


def _consume_operational_state_notification(envelope: EventEnvelope):
    return consume_operational_state_notification(
        envelope,
        administrator_id_provider=active_administrator_id,
    )


def _consume_opportunity_notification(envelope: EventEnvelope):
    return consume_opportunity_notification(
        envelope,
        administrator_id_provider=active_administrator_id,
    )


def _consume_export_final_failure(envelope: EventEnvelope):
    if envelope.payload.get("task_name") != "apps.exchange.build_export":
        return None
    from config.exchange_integrations import configured_export_storage

    return consume_export_task_final_failure(
        envelope,
        storage=configured_export_storage(),
    )


def _consume_backup_final_failure(envelope: EventEnvelope):
    if envelope.payload.get("task_name") != "apps.operations.weekly_backup":
        return None
    from config.backup_integrations import configured_backup_storage

    return consume_backup_task_final_failure(
        envelope,
        storage=configured_backup_storage(),
    )


def _routes(event_type: str) -> tuple[EventConsumer, ...]:
    if event_type == "account.author_role_changed.v1":
        return (consume_author_role_changed,)
    if event_type in {"account.disabled.v1", "account.enabled.v1"}:
        return (consume_account_status_event,)
    if event_type == "account.deleted.v1":
        return (consume_moderation_account_deleted, consume_account_deleted)
    if event_type in _ARTICLE_MODERATION_EVENTS:
        return (consume_discovery_cache_event, consume_domain_notification)
    if event_type == "section.changed.v1":
        return (consume_discovery_cache_event, consume_navigation_section_event)
    if event_type in _DISCOVERY_EVENTS:
        return (consume_discovery_cache_event,)
    if event_type in _DOMAIN_NOTIFICATION_EVENTS:
        return (consume_domain_notification,)
    if event_type == "task.final_failed.v1":
        return (
            _consume_export_final_failure,
            _consume_backup_final_failure,
            consume_task_final_failure_alert,
            _consume_task_final_failure_notification,
        )
    if event_type in {
        "capacity.threshold_changed.v1",
        "service.health_changed.v1",
    }:
        return (_consume_operational_state_notification,)
    if event_type in {
        "opportunity.source_state_changed.v1",
        "opportunity.check_summary.v1",
        "opportunity.check_stalled.v1",
    }:
        return (_consume_opportunity_notification,)
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
