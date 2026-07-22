from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.core.events import ConsumerOutcome, EventEnvelope
from apps.core.events.models import ConsumerStatus, EventConsumerRecord
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.notifications.consumers import account_events
from apps.notifications.consumers.account_events import (
    consume_account_deleted,
    consume_author_role_changed,
)
from apps.notifications.models import Notification, NotificationReceipt
from apps.notifications.services.delivery import registered_notification_templates
from tests.fixtures.accounts import create_test_account, delete_test_account

pytestmark = pytest.mark.django_db(transaction=True)


def _envelope(*, event_type: str, account_id, payload) -> EventEnvelope:
    return EventEnvelope(
        event_id=new_ulid(),
        event_type=event_type,
        schema_version=1,
        occurred_at=timezone.now(),
        actor_id=None,
        aggregate_type="account",
        aggregate_id=str(account_id),
        trace_code=new_trace_code(),
        payload=payload,
    )


def _role_event(account_id, *, enabled=True) -> EventEnvelope:
    return _envelope(
        event_type="account.author_role_changed.v1",
        account_id=account_id,
        payload={"enabled": enabled},
    )


def _deleted_event(account_id) -> EventEnvelope:
    return _envelope(
        event_type="account.deleted.v1",
        account_id=account_id,
        payload={
            "deletion_id": new_ulid(),
            "was_author": False,
            "author_disposition": "no_articles",
            "disposition_id": new_ulid(),
            "article_count": 0,
        },
    )


def test_role_event_delivers_one_safe_notification_for_duplicate_delivery():
    recipient = create_test_account(email="notification-target@kaj.test")
    envelope = _role_event(recipient.id)

    first = consume_author_role_changed(envelope)
    duplicate = consume_author_role_changed(envelope)

    assert first.outcome == ConsumerOutcome.PROCESSED
    assert duplicate.outcome == ConsumerOutcome.ALREADY_PROCESSED
    assert Notification.objects.count() == 1
    receipt = NotificationReceipt.objects.select_related("notification").get()
    assert receipt.recipient_id == recipient.id
    assert receipt.notification.template_key == "account.author_role_changed.v1"
    assert receipt.notification.target_id == str(recipient.id)
    assert receipt.notification.payload_safe == {"enabled": True}
    assert recipient.email not in str(receipt.notification.payload_safe)
    assert EventConsumerRecord.objects.get().attempts == 1


def test_status_events_have_no_notification_template():
    templates = registered_notification_templates()
    assert "account.author_role_changed.v1" in templates
    assert "account.disabled.v1" not in templates
    assert "account.enabled.v1" not in templates


def test_role_notification_becomes_safe_noop_if_recipient_was_deleted():
    recipient = create_test_account(email="deleted-notification-target@kaj.test")
    envelope = _role_event(recipient.id)
    delete_test_account(recipient.id)

    result = consume_author_role_changed(envelope)
    assert result.outcome == ConsumerOutcome.PROCESSED
    assert Notification.objects.count() == 0


def test_account_deletion_consumer_removes_only_orphaned_notifications():
    recipient = create_test_account(email="notification-cleanup@kaj.test")
    consume_author_role_changed(_role_event(recipient.id))
    assert NotificationReceipt.objects.count() == 1
    delete_test_account(recipient.id)
    assert NotificationReceipt.objects.count() == 0
    assert Notification.objects.count() == 1
    envelope = _deleted_event(recipient.id)

    first = consume_account_deleted(envelope)
    duplicate = consume_account_deleted(envelope)
    assert first.outcome == ConsumerOutcome.PROCESSED
    assert duplicate.outcome == ConsumerOutcome.ALREADY_PROCESSED
    assert Notification.objects.count() == 0


def test_role_consumer_retries_transactionally_then_reaches_final_state(
    monkeypatch,
):
    recipient = create_test_account(email="notification-retry@kaj.test")
    envelope = _role_event(recipient.id)
    start = datetime(2026, 7, 22, 6, 0, tzinfo=UTC)
    original = account_events.deliver_notification

    def fail_once(**kwargs):
        del kwargs
        raise RuntimeError("delivery unavailable")

    monkeypatch.setattr(account_events, "deliver_notification", fail_once)
    with pytest.raises(RuntimeError, match="delivery unavailable"):
        consume_author_role_changed(
            envelope,
            clock=FrozenClock(start),
            retry_delay_seconds=1,
        )
    record = EventConsumerRecord.objects.get()
    assert record.status == ConsumerStatus.PENDING
    assert record.attempts == 1
    assert Notification.objects.count() == 0

    monkeypatch.setattr(account_events, "deliver_notification", original)
    result = consume_author_role_changed(
        envelope,
        clock=FrozenClock(start + timedelta(seconds=2)),
        retry_delay_seconds=1,
    )
    record.refresh_from_db()
    assert result.outcome == ConsumerOutcome.PROCESSED
    assert record.status == ConsumerStatus.PROCESSED
    assert record.attempts == 2
    assert Notification.objects.count() == 1
