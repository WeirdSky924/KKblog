import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from django.db import transaction

from apps.core.ids import new_uuid
from apps.core.time.clock import Clock, SystemClock

from .envelope import EventEnvelope
from .models import ConsumerStatus, EventConsumerRecord
from .publisher import _positive

logger = logging.getLogger("kaj.event_consumers")
_CONSUMER_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_CONSUMER_ERROR = "core.event_consumer_failed.v1"
ConsumerHandler = Callable[[EventEnvelope], None]


class ConsumerOutcome(StrEnum):
    PROCESSED = "processed"
    ALREADY_PROCESSED = "already_processed"
    BUSY = "busy"


@dataclass(frozen=True, slots=True)
class ConsumerResult:
    outcome: ConsumerOutcome
    attempt: int


@dataclass(frozen=True, slots=True)
class _ConsumerClaim:
    record_id: int
    lease_token: UUID
    attempt: int


def _claim_consumer(
    envelope: EventEnvelope,
    consumer_name: str,
    *,
    lease_seconds: int,
    clock: Clock,
) -> _ConsumerClaim | ConsumerResult:
    if not isinstance(consumer_name, str) or not _CONSUMER_NAME.fullmatch(
        consumer_name
    ):
        raise ValueError("Invalid consumer_name")
    _positive(lease_seconds, "lease_seconds", 3_600)
    now = clock.now()
    with transaction.atomic():
        record, _ = EventConsumerRecord.objects.select_for_update().get_or_create(
            event_id=envelope.event_id,
            consumer_name=consumer_name,
            defaults={
                "event_type": envelope.event_type,
                "trace_code": envelope.trace_code,
                "available_at": now,
            },
        )
        if record.event_type != envelope.event_type:
            raise ValueError("Consumer record event type mismatch")
        if record.status == ConsumerStatus.PROCESSED:
            return ConsumerResult(ConsumerOutcome.ALREADY_PROCESSED, record.attempts)
        if record.available_at > now or (
            record.lease_expires_at is not None and record.lease_expires_at > now
        ):
            return ConsumerResult(ConsumerOutcome.BUSY, record.attempts)

        lease_token = new_uuid()
        record.status = ConsumerStatus.PROCESSING
        record.lease_token = lease_token
        record.lease_expires_at = now + timedelta(seconds=lease_seconds)
        record.attempts += 1
        record.trace_code = envelope.trace_code
        record.save(
            update_fields=(
                "status",
                "lease_token",
                "lease_expires_at",
                "attempts",
                "trace_code",
                "updated_at",
            )
        )
        return _ConsumerClaim(record.pk, lease_token, record.attempts)


def _mark_consumer_failed(
    claim: _ConsumerClaim,
    *,
    retry_delay_seconds: int,
    clock: Clock,
) -> None:
    EventConsumerRecord.objects.filter(
        pk=claim.record_id,
        status=ConsumerStatus.PROCESSING,
        lease_token=claim.lease_token,
    ).update(
        status=ConsumerStatus.PENDING,
        available_at=clock.now() + timedelta(seconds=retry_delay_seconds),
        lease_token=None,
        lease_expires_at=None,
        last_error_code=_CONSUMER_ERROR,
    )


def consume_once(
    envelope: EventEnvelope,
    consumer_name: str,
    handler: ConsumerHandler,
    *,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
) -> ConsumerResult:
    if not callable(handler):
        raise TypeError("Consumer handler must be callable")
    _positive(retry_delay_seconds, "retry_delay_seconds", 86_400)
    active_clock = clock or SystemClock()
    claim = _claim_consumer(
        envelope,
        consumer_name,
        lease_seconds=lease_seconds,
        clock=active_clock,
    )
    if isinstance(claim, ConsumerResult):
        return claim

    try:
        with transaction.atomic():
            record = EventConsumerRecord.objects.select_for_update().get(
                pk=claim.record_id,
                status=ConsumerStatus.PROCESSING,
                lease_token=claim.lease_token,
            )
            handler(envelope)
            record.status = ConsumerStatus.PROCESSED
            record.processed_at = active_clock.now()
            record.lease_token = None
            record.lease_expires_at = None
            record.last_error_code = ""
            record.save(
                update_fields=(
                    "status",
                    "processed_at",
                    "lease_token",
                    "lease_expires_at",
                    "last_error_code",
                    "updated_at",
                )
            )
    except Exception:
        _mark_consumer_failed(
            claim,
            retry_delay_seconds=retry_delay_seconds,
            clock=active_clock,
        )
        logger.error(
            "Event consumer failed consumer=%s event_type=%s",
            consumer_name,
            envelope.event_type,
            extra={"trace_code": envelope.trace_code},
        )
        raise
    return ConsumerResult(ConsumerOutcome.PROCESSED, claim.attempt)
