from collections.abc import Mapping
from uuid import UUID

from django.db import connection
from django.db.transaction import TransactionManagementError

from apps.core.ids import new_ulid
from apps.core.observability.context import current_trace_code
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import Clock, SystemClock

from .envelope import EventDefinition, EventEnvelope
from .models import OutboxEvent


def enqueue_event(
    definition: EventDefinition,
    *,
    aggregate_type: str,
    aggregate_id: str,
    payload: Mapping[str, object],
    actor_id: UUID | None = None,
    trace_code: str | None = None,
    clock: Clock | None = None,
) -> EventEnvelope:
    """Persist an event in the caller's active business transaction."""
    if not connection.in_atomic_block:
        raise TransactionManagementError(
            "Outbox events must be written inside transaction.atomic()"
        )
    active_clock = clock or SystemClock()
    occurred_at = active_clock.now()
    envelope = EventEnvelope(
        event_id=new_ulid(),
        event_type=definition.event_type,
        schema_version=definition.schema_version,
        occurred_at=occurred_at,
        actor_id=actor_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        trace_code=trace_code or current_trace_code() or new_trace_code(),
        payload=definition.validate_payload(payload),
    )
    OutboxEvent.objects.create(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        schema_version=envelope.schema_version,
        occurred_at=envelope.occurred_at,
        actor_id=envelope.actor_id,
        aggregate_type=envelope.aggregate_type,
        aggregate_id=envelope.aggregate_id,
        trace_code=envelope.trace_code,
        payload=dict(envelope.payload),
        available_at=occurred_at,
    )
    return envelope


def envelope_from_model(event: OutboxEvent) -> EventEnvelope:
    return EventEnvelope(
        event_id=event.event_id,
        event_type=event.event_type,
        schema_version=event.schema_version,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        trace_code=event.trace_code,
        payload=event.payload,
    )
