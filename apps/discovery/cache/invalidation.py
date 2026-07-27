from __future__ import annotations

from uuid import UUID

from apps.content.public import article_ids_by_author_for_cache
from apps.core.events import ConsumerResult, EventEnvelope, consume_once
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock

from .renderer import RedisDiscoveryCache, default_discovery_cache

CONSUMER_NAME = "discovery.public-cache.v1"
ARTICLE_EVENT_TYPES = frozenset(
    {
        "article.published.v1",
        "article.visibility_changed.v1",
        "article.hidden.v1",
        "article.deleted.v1",
        "article.restored.v1",
        "article.purge_requested.v1",
        "article.moderated.v1",
        "article.moderation_restored.v1",
        "article.moderation_finalized.v1",
    }
)
CLASSIFICATION_EVENT_TYPES = frozenset({"section.changed.v1", "tag.changed.v1"})
AUTHOR_EVENT_TYPE = "article.author_mask_changed.v1"
SUPPORTED_EVENT_TYPES = (
    ARTICLE_EVENT_TYPES | CLASSIFICATION_EVENT_TYPES | {AUTHOR_EVENT_TYPE}
)


class DiscoveryCacheEventError(ValueError):
    pass


class DiscoveryCacheUnavailable(RuntimeError):
    pass


def _event_identity(envelope: EventEnvelope) -> tuple[str, str]:
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.schema_version != 1
        or envelope.event_type not in SUPPORTED_EVENT_TYPES
    ):
        raise DiscoveryCacheEventError("Invalid discovery cache event")
    if envelope.event_type in ARTICLE_EVENT_TYPES:
        if envelope.aggregate_type != "article":
            raise DiscoveryCacheEventError("Invalid discovery cache event")
        try:
            return "article", normalize_ulid(envelope.aggregate_id)
        except (TypeError, ValueError):
            raise DiscoveryCacheEventError("Invalid discovery cache event") from None
    expected_type = (
        "author"
        if envelope.event_type == AUTHOR_EVENT_TYPE
        else envelope.event_type.split(".", 1)[0]
    )
    if envelope.aggregate_type != expected_type:
        raise DiscoveryCacheEventError("Invalid discovery cache event")
    try:
        return expected_type, str(UUID(envelope.aggregate_id))
    except (TypeError, ValueError):
        raise DiscoveryCacheEventError("Invalid discovery cache event") from None


def _apply_event(
    envelope: EventEnvelope,
    *,
    cache: RedisDiscoveryCache,
) -> None:
    aggregate_type, aggregate_id = _event_identity(envelope)
    if aggregate_type == "article":
        cache.invalidate(article_ids=(aggregate_id,))
    elif aggregate_type == "author":
        cache.invalidate(
            article_ids=article_ids_by_author_for_cache(author_id=aggregate_id)
        )
    else:
        cache.invalidate()


def consume_discovery_cache_event(
    envelope: EventEnvelope,
    *,
    cache: RedisDiscoveryCache | None = None,
    clock: Clock | None = None,
) -> ConsumerResult:
    _event_identity(envelope)
    active_cache = cache or default_discovery_cache()
    if active_cache is None:
        raise DiscoveryCacheUnavailable("Discovery cache is not configured")
    active_clock = clock or SystemClock()
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: _apply_event(item, cache=active_cache),
        clock=active_clock,
    )
