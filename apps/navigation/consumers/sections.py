from uuid import UUID

from apps.core.events import ConsumerResult, EventEnvelope, consume_once

from ..queries import invalidate_public_navigation_cache

CONSUMER_NAME = "navigation.section-cache.v1"


class NavigationSectionEventError(ValueError):
    pass


def _validate(envelope: EventEnvelope) -> None:
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.event_type != "section.changed.v1"
        or envelope.schema_version != 1
        or envelope.aggregate_type != "section"
    ):
        raise NavigationSectionEventError("Invalid navigation section event")
    try:
        UUID(envelope.aggregate_id)
    except (TypeError, ValueError):
        raise NavigationSectionEventError("Invalid navigation section event") from None


def consume_navigation_section_event(envelope: EventEnvelope) -> ConsumerResult:
    _validate(envelope)
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda _item: invalidate_public_navigation_cache(),
    )


__all__ = [
    "NavigationSectionEventError",
    "consume_navigation_section_event",
]
