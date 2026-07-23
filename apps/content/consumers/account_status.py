from uuid import UUID

from django.db import transaction
from django.db.models import Q

from apps.core.events import ConsumerResult, EventEnvelope, consume_once, enqueue_event
from apps.core.time.clock import Clock, SystemClock

from ..events import ARTICLE_SCHEDULE_CANCELLED, AUTHOR_MASK_CHANGED
from ..models import Article, ArticleTombstone, AuthorContentMask

CONSUMER_NAME = "content.account-status.v1"
STATUS_EVENT_TYPES = frozenset({"account.disabled.v1", "account.enabled.v1"})


class AccountStatusEventError(ValueError):
    pass


def _author_id(envelope: EventEnvelope) -> UUID:
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.event_type not in STATUS_EVENT_TYPES
        or envelope.schema_version != 1
        or envelope.aggregate_type != "account"
        or envelope.payload
    ):
        raise AccountStatusEventError("Invalid account status event")
    try:
        return UUID(envelope.aggregate_id)
    except (TypeError, ValueError):
        raise AccountStatusEventError("Invalid account status event") from None


def _is_newer(mask: AuthorContentMask, envelope: EventEnvelope) -> bool:
    return (envelope.occurred_at, envelope.event_id) > (
        mask.last_event_at,
        mask.last_event_id,
    )


def _cancel_schedules(envelope: EventEnvelope, author_id: UUID, clock: Clock) -> int:
    articles = list(
        Article.objects.select_for_update()
        .filter(
            author_id=author_id,
            publication_state=Article.PublicationState.SCHEDULED,
            scheduled_revision__isnull=False,
        )
        .filter(
            Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=envelope.occurred_at)
        )
        .order_by("id")
    )
    for article in articles:
        revision_id = article.scheduled_revision_id
        article.publication_state = Article.PublicationState.DRAFT
        article.scheduled_revision = None
        article.scheduled_for = None
        article.scheduled_at = None
        article.row_version += 1
        article.save(
            update_fields=(
                "publication_state",
                "scheduled_revision",
                "scheduled_for",
                "scheduled_at",
                "row_version",
                "updated_at",
            )
        )
        enqueue_event(
            ARTICLE_SCHEDULE_CANCELLED,
            aggregate_type="article",
            aggregate_id=article.id,
            actor_id=envelope.actor_id,
            trace_code=envelope.trace_code,
            payload={"revision_id": revision_id},
            clock=clock,
        )
    ArticleTombstone.objects.select_for_update().filter(
        author_id=author_id,
        purged_at__isnull=True,
        original_publication_state=Article.PublicationState.SCHEDULED,
    ).filter(
        Q(original_scheduled_at__isnull=True)
        | Q(original_scheduled_at__lte=envelope.occurred_at)
    ).update(
        original_publication_state=Article.PublicationState.DRAFT,
        original_scheduled_revision_id=None,
        original_scheduled_for=None,
        original_scheduled_at=None,
    )
    return len(articles)


def _apply_status_event(envelope: EventEnvelope, *, clock: Clock) -> None:
    author_id = _author_id(envelope)
    disabled = envelope.event_type == "account.disabled.v1"
    with transaction.atomic():
        mask, created = AuthorContentMask.objects.select_for_update().get_or_create(
            author_id=author_id,
            defaults={
                "masked": disabled,
                "last_event_at": envelope.occurred_at,
                "last_event_id": envelope.event_id,
                "last_event_type": envelope.event_type,
            },
        )
        projection_changed = created
        if not created and _is_newer(mask, envelope):
            projection_changed = mask.masked != disabled
            mask.masked = disabled
            mask.last_event_at = envelope.occurred_at
            mask.last_event_id = envelope.event_id
            mask.last_event_type = envelope.event_type
            mask.save(
                update_fields=(
                    "masked",
                    "last_event_at",
                    "last_event_id",
                    "last_event_type",
                    "updated_at",
                )
            )
        cancelled_count = (
            _cancel_schedules(envelope, author_id, clock) if disabled else 0
        )
        if projection_changed or cancelled_count:
            enqueue_event(
                AUTHOR_MASK_CHANGED,
                aggregate_type="author",
                aggregate_id=str(author_id),
                actor_id=envelope.actor_id,
                trace_code=envelope.trace_code,
                payload={
                    "masked": mask.masked,
                    "article_count": Article.objects.filter(
                        author_id=author_id
                    ).count(),
                    "cancelled_count": cancelled_count,
                },
                clock=clock,
            )


def consume_account_status_event(
    envelope: EventEnvelope,
    *,
    clock: Clock | None = None,
) -> ConsumerResult:
    active_clock = clock or SystemClock()
    _author_id(envelope)
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: _apply_status_event(item, clock=active_clock),
        clock=active_clock,
    )
