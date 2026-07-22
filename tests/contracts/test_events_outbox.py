from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import override_settings

from apps.core.events import (
    ConsumerOutcome,
    EventDefinition,
    EventValidationError,
    consume_once,
    enqueue_event,
    publish_batch,
)
from apps.core.events.models import (
    ConsumerStatus,
    EventConsumerRecord,
    OutboxEvent,
    OutboxStatus,
)
from apps.core.time.clock import FrozenClock

BASE_TIME = datetime(2026, 7, 21, 3, 0, tzinfo=UTC)


def _account_schema(payload) -> None:
    if set(payload) != {"account_id"} or not isinstance(payload["account_id"], str):
        raise ValueError


ACCOUNT_REGISTERED = EventDefinition("account.registered.v1", _account_schema)
DERIVED_EVENT = EventDefinition("test.effect_recorded.v1", _account_schema)


@pytest.fixture(autouse=True)
def require_postgresql() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("FND-005 contract tests require isolated PostgreSQL")


def _enqueue(*, clock=None):
    with transaction.atomic():
        return enqueue_event(
            ACCOUNT_REGISTERED,
            aggregate_type="account",
            aggregate_id="4fd0a343-2258-46f4-8747-aa079e2dd15a",
            payload={"account_id": "4fd0a343-2258-46f4-8747-aa079e2dd15a"},
            clock=clock or FrozenClock(BASE_TIME),
        )


class RecordingTransport:
    def __init__(self) -> None:
        self.event_ids = []

    def publish(self, envelope) -> None:
        self.event_ids.append(envelope.event_id)


COMMAND_DELIVERIES = []


def build_command_transport():
    class CommandTransport:
        def publish(self, envelope) -> None:
            COMMAND_DELIVERIES.append(envelope.event_id)

    return CommandTransport()


def build_broken_command_transport():
    raise RuntimeError("transport-factory-private-sentinel")


@pytest.mark.django_db(transaction=True)
def test_outbox_requires_and_rolls_back_with_business_transaction() -> None:
    with pytest.raises(transaction.TransactionManagementError):
        enqueue_event(
            ACCOUNT_REGISTERED,
            aggregate_type="account",
            aggregate_id="4fd0a343-2258-46f4-8747-aa079e2dd15a",
            payload={"account_id": "4fd0a343-2258-46f4-8747-aa079e2dd15a"},
        )

    with pytest.raises(RuntimeError), transaction.atomic():
        enqueue_event(
            ACCOUNT_REGISTERED,
            aggregate_type="account",
            aggregate_id="4fd0a343-2258-46f4-8747-aa079e2dd15a",
            payload={"account_id": "4fd0a343-2258-46f4-8747-aa079e2dd15a"},
        )
        raise RuntimeError("simulated pre-commit crash")
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_publisher_retries_after_post_publish_crash_and_lease_expiry() -> None:
    envelope = _enqueue()

    class ProcessCrash(BaseException):
        pass

    first_delivery = RecordingTransport()

    class CrashAfterPublish:
        def publish(self, item) -> None:
            first_delivery.publish(item)
            raise ProcessCrash

    with pytest.raises(ProcessCrash):
        publish_batch(
            CrashAfterPublish(),
            lease_seconds=10,
            clock=FrozenClock(BASE_TIME),
        )
    event = OutboxEvent.objects.get()
    assert event.status == OutboxStatus.PENDING
    assert event.attempts == 1
    assert event.lease_expires_at == BASE_TIME + timedelta(seconds=10)

    second_delivery = RecordingTransport()
    busy = publish_batch(
        second_delivery,
        lease_seconds=10,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=9)),
    )
    assert busy.claimed == 0

    recovered = publish_batch(
        second_delivery,
        lease_seconds=10,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=11)),
    )
    event.refresh_from_db()
    assert recovered.published == 1
    assert event.status == OutboxStatus.PUBLISHED
    assert event.attempts == 2
    assert event.published_at == BASE_TIME + timedelta(seconds=11)
    assert first_delivery.event_ids + second_delivery.event_ids == [
        envelope.event_id,
        envelope.event_id,
    ]


@pytest.mark.django_db(transaction=True)
def test_normal_transport_failure_stays_pending_until_retry() -> None:
    _enqueue()

    class FailedTransport:
        def publish(self, envelope) -> None:
            del envelope
            raise RuntimeError("sensitive transport detail")

    result = publish_batch(
        FailedTransport(),
        retry_delay_seconds=30,
        clock=FrozenClock(BASE_TIME),
    )
    event = OutboxEvent.objects.get()
    assert result.failed == 1
    assert event.status == OutboxStatus.PENDING
    assert event.last_error_code == "core.outbox_transport_failed.v1"
    assert event.available_at == BASE_TIME + timedelta(seconds=30)
    assert event.lease_token is None

    transport = RecordingTransport()
    result = publish_batch(
        transport,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=31)),
    )
    event.refresh_from_db()
    assert result.published == 1
    assert event.status == OutboxStatus.PUBLISHED


@pytest.mark.django_db(transaction=True)
def test_consumer_deduplicates_database_side_effect() -> None:
    envelope = _enqueue()

    def create_effect(item) -> None:
        enqueue_event(
            DERIVED_EVENT,
            aggregate_type="account",
            aggregate_id=item.aggregate_id,
            payload={"account_id": item.aggregate_id},
            clock=FrozenClock(BASE_TIME),
        )

    first = consume_once(
        envelope,
        "tests.account_projection.v1",
        create_effect,
        clock=FrozenClock(BASE_TIME),
    )
    duplicate = consume_once(
        envelope,
        "tests.account_projection.v1",
        create_effect,
        clock=FrozenClock(BASE_TIME),
    )
    record = EventConsumerRecord.objects.get()
    assert first.outcome == ConsumerOutcome.PROCESSED
    assert duplicate.outcome == ConsumerOutcome.ALREADY_PROCESSED
    assert record.status == ConsumerStatus.PROCESSED
    assert record.attempts == 1
    assert record.processed_at == BASE_TIME
    assert OutboxEvent.objects.filter(event_type=DERIVED_EVENT.event_type).count() == 1


@pytest.mark.django_db(transaction=True)
def test_consumer_failure_rolls_back_effect_and_retries() -> None:
    envelope = _enqueue()

    def fail_after_effect(item) -> None:
        enqueue_event(
            DERIVED_EVENT,
            aggregate_type="account",
            aggregate_id=item.aggregate_id,
            payload={"account_id": item.aggregate_id},
            clock=FrozenClock(BASE_TIME),
        )
        raise RuntimeError("sensitive consumer detail")

    with pytest.raises(RuntimeError):
        consume_once(
            envelope,
            "tests.retrying_projection.v1",
            fail_after_effect,
            retry_delay_seconds=20,
            clock=FrozenClock(BASE_TIME),
        )
    record = EventConsumerRecord.objects.get()
    assert record.status == ConsumerStatus.PENDING
    assert record.last_error_code == "core.event_consumer_failed.v1"
    assert OutboxEvent.objects.filter(event_type=DERIVED_EVENT.event_type).count() == 0

    def succeed(item) -> None:
        enqueue_event(
            DERIVED_EVENT,
            aggregate_type="account",
            aggregate_id=item.aggregate_id,
            payload={"account_id": item.aggregate_id},
            clock=FrozenClock(BASE_TIME + timedelta(seconds=21)),
        )

    result = consume_once(
        envelope,
        "tests.retrying_projection.v1",
        succeed,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=21)),
    )
    record.refresh_from_db()
    assert result.outcome == ConsumerOutcome.PROCESSED
    assert record.status == ConsumerStatus.PROCESSED
    assert record.attempts == 2
    assert OutboxEvent.objects.filter(event_type=DERIVED_EVENT.event_type).count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "not-recorded"},
        {"nested": {"verification_code": "not-recorded"}},
        {"safe": "postgresql://user:not-recorded@localhost/kaj"},
        {"safe": "Bearer not-recorded-token"},
    ],
)
def test_event_contract_rejects_sensitive_payload(payload) -> None:
    with pytest.raises(EventValidationError):
        ACCOUNT_REGISTERED.validate_payload(payload)


@pytest.mark.parametrize(
    "event_type",
    ["account.registered", "account.registered.v0", "Account.registered.v1"],
)
def test_event_contract_requires_stable_positive_version(event_type) -> None:
    with pytest.raises(EventValidationError):
        EventDefinition(event_type, _account_schema)


def test_event_contract_runs_version_specific_schema() -> None:
    with pytest.raises(EventValidationError):
        ACCOUNT_REGISTERED.validate_payload({"account_id": 42})


@pytest.mark.django_db(transaction=True)
def test_management_command_fails_closed_without_transport() -> None:
    _enqueue()
    with pytest.raises(CommandError, match="OUTBOX_TRANSPORT is required"):
        call_command("publish_outbox")
    assert OutboxEvent.objects.get().status == OutboxStatus.PENDING


@pytest.mark.django_db(transaction=True)
@override_settings(
    OUTBOX_TRANSPORT=(
        "tests.contracts.test_events_outbox.build_broken_command_transport"
    )
)
def test_management_command_redacts_transport_factory_failure() -> None:
    with pytest.raises(CommandError) as captured:
        call_command("publish_outbox")
    assert "transport-factory-private-sentinel" not in str(captured.value)


@pytest.mark.django_db(transaction=True)
@override_settings(
    OUTBOX_TRANSPORT="tests.contracts.test_events_outbox.build_command_transport"
)
def test_management_command_publishes_explicit_transport() -> None:
    COMMAND_DELIVERIES.clear()
    envelope = _enqueue()
    output = StringIO()
    call_command("publish_outbox", stdout=output)
    event = OutboxEvent.objects.get()
    assert event.status == OutboxStatus.PUBLISHED
    assert COMMAND_DELIVERIES == [envelope.event_id]
    assert "claimed=1 published=1 failed=0" in output.getvalue()
    assert envelope.event_id not in output.getvalue()
