from datetime import UTC, datetime, timedelta

import pytest
from django.apps import apps
from django.urls import reverse

from apps.core.events import EventEnvelope
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.notifications.consumers.domain_events import consume_domain_notification
from apps.notifications.models import Notification
from apps.notifications.public import mark_target_notifications_read
from apps.notifications.queries import notification_popover
from apps.notifications.templates_registry import (
    register_builtin_templates,
    render_notification,
)
from apps.operations.models import TaskRun, TaskRunStatus
from apps.operations.queries.tasks import task_run_records

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    return apps.get_model("accounts", "Account").objects.create_account(
        email=f"{label}@kaj.test", password="Valid-password-1"
    )


def test_learning_terminal_notification_is_safe_deduplicated_readable_and_linked():
    register_builtin_templates()
    recipient = _account("learning-t19-recipient")
    bank_id = "3d7b8be5-2f25-4f1a-96ee-7b9f9d6e0019"
    envelope = EventEnvelope(
        event_id=new_ulid(),
        event_type="learning.generation_partial.v1",
        schema_version=1,
        occurred_at=datetime(2026, 8, 18, tzinfo=UTC),
        actor_id=None,
        aggregate_type="question_bank_series",
        aggregate_id=bank_id,
        trace_code=new_trace_code(),
        payload={"recipient_id": str(recipient.id)},
    )
    first = consume_domain_notification(envelope)
    second = consume_domain_notification(envelope)
    assert first.outcome.value == "processed"
    assert second.outcome.value == "already_processed"
    assert Notification.objects.count() == 1
    item = notification_popover(recipient_id=recipient.id).items[0]
    assert item.target_url == reverse("learning:documents")
    assert "<script" not in item.message_html.lower()
    assert (
        mark_target_notifications_read(
            recipient_id=recipient.id,
            target_type="question_bank_series",
        )
        == 1
    )
    assert notification_popover(recipient_id=recipient.id).unread_count == 0
    rendered = render_notification("learning.generation_partial.v1", {})
    assert rendered.title == "题库已按容量生成"
    assert "部分知识点" in rendered.message


def test_task_projection_exposes_duration_without_private_diagnostics():
    started = datetime(2026, 8, 18, 1, tzinfo=UTC)
    TaskRun.objects.create(
        run_id=new_ulid(),
        task_name="apps.learning.review_knowledge_document",
        business_object="knowledge-review:public",
        idempotency_key="t19-task-projection",
        celery_id="t19-celery",
        trace_code=new_trace_code(),
        status=TaskRunStatus.SUCCEEDED,
        attempt=1,
        scheduled_at=started,
        available_at=started,
        started_at=started,
        completed_at=started + timedelta(seconds=7),
        result_ref="review:done",
    )
    item = task_run_records(is_admin=True)[0]
    assert item.duration_seconds == 7
    assert item.token_requested is None
    assert item.token_settled is None
    assert "private" not in str(item)
