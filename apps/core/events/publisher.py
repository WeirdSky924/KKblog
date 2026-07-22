import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from django.db import transaction
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.core.time.clock import Clock, SystemClock

from .envelope import EventEnvelope
from .models import OutboxEvent, OutboxStatus
from .outbox import envelope_from_model

logger = logging.getLogger("kaj.outbox")
_TRANSPORT_ERROR = "core.outbox_transport_failed.v1"


class EventTransport(Protocol):
    def publish(self, envelope: EventEnvelope) -> None: ...


@dataclass(frozen=True, slots=True)
class ClaimedEvent:
    envelope: EventEnvelope
    lease_token: UUID


@dataclass(frozen=True, slots=True)
class PublishResult:
    claimed: int
    published: int
    failed: int


def _positive(value: int, name: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def claim_pending_events(
    *,
    batch_size: int,
    lease_seconds: int,
    clock: Clock,
) -> tuple[ClaimedEvent, ...]:
    _positive(batch_size, "batch_size", 1_000)
    _positive(lease_seconds, "lease_seconds", 3_600)
    now = clock.now()
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    claimed: list[ClaimedEvent] = []
    with transaction.atomic():
        events = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxStatus.PENDING, available_at__lte=now)
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
            .order_by("occurred_at", "event_id")[:batch_size]
        )
        for event in events:
            lease_token = new_uuid()
            event.lease_token = lease_token
            event.lease_expires_at = lease_expires_at
            event.attempts += 1
            event.save(
                update_fields=(
                    "lease_token",
                    "lease_expires_at",
                    "attempts",
                )
            )
            claimed.append(ClaimedEvent(envelope_from_model(event), lease_token))
    return tuple(claimed)


def _mark_published(claim: ClaimedEvent, *, clock: Clock) -> bool:
    return bool(
        OutboxEvent.objects.filter(
            event_id=claim.envelope.event_id,
            status=OutboxStatus.PENDING,
            lease_token=claim.lease_token,
        ).update(
            status=OutboxStatus.PUBLISHED,
            published_at=clock.now(),
            lease_token=None,
            lease_expires_at=None,
            last_error_code="",
        )
    )


def _mark_failed(
    claim: ClaimedEvent,
    *,
    clock: Clock,
    retry_delay_seconds: int,
) -> None:
    OutboxEvent.objects.filter(
        event_id=claim.envelope.event_id,
        status=OutboxStatus.PENDING,
        lease_token=claim.lease_token,
    ).update(
        available_at=clock.now() + timedelta(seconds=retry_delay_seconds),
        lease_token=None,
        lease_expires_at=None,
        last_error_code=_TRANSPORT_ERROR,
    )


def publish_batch(
    transport: EventTransport,
    *,
    batch_size: int = 100,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
) -> PublishResult:
    if not callable(getattr(transport, "publish", None)):
        raise TypeError("Outbox transport must provide publish(envelope)")
    _positive(retry_delay_seconds, "retry_delay_seconds", 86_400)
    active_clock = clock or SystemClock()
    claims = claim_pending_events(
        batch_size=batch_size,
        lease_seconds=lease_seconds,
        clock=active_clock,
    )
    published = 0
    failed = 0
    for claim in claims:
        try:
            transport.publish(claim.envelope)
        except Exception:
            failed += 1
            _mark_failed(
                claim,
                clock=active_clock,
                retry_delay_seconds=retry_delay_seconds,
            )
            logger.error(
                "Outbox transport failed event_type=%s",
                claim.envelope.event_type,
                extra={"trace_code": claim.envelope.trace_code},
            )
            continue
        if _mark_published(claim, clock=active_clock):
            published += 1
    return PublishResult(len(claims), published, failed)


TransportFactory = Callable[[], EventTransport]
