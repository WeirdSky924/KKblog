import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from celery.exceptions import Retry
from django.apps import apps
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.content.models import Article
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    PublicationCommandError,
    cancel_schedule,
    create_article,
    create_section,
    delete_section,
    prepare_publication,
    publish_scheduled_article,
    published_revision,
    save_revision,
    schedule_article,
)
from apps.content.tasks import publication as publication_tasks
from apps.content.tasks.publication import publish_scheduled_article_task
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.operations.public import RetryableTaskError

pytestmark = pytest.mark.django_db(transaction=True)
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _admin(label: str = "schedule-admin"):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _snapshot(section_id, body: str) -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title="排期文章",
        body=body,
        section_id=section_id,
    )


def _setup(label: str = "schedule"):
    admin = _admin(label)
    section = create_section(actor_id=admin.id, name="排期分区", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, "排期版本"),
        capacity_check=lambda: None,
    )
    return admin, section, article


def _schedule(admin, article, when_local: datetime, now: datetime):
    review = prepare_publication(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        clock=FrozenClock(now),
    )
    return schedule_article(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
        review_token=review.token,
        scheduled_local=when_local,
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )


def test_schedule_uses_shanghai_input_and_utc_fact() -> None:
    admin, _, article = _setup("timezone")
    now = datetime(2026, 7, 23, 0, 0, tzinfo=UTC)
    scheduled = _schedule(admin, article, datetime(2026, 7, 24, 9, 30), now)

    aggregate = Article.objects.get(pk=article.article_id)
    assert scheduled.scheduled_for == datetime(2026, 7, 24, 1, 30, tzinfo=UTC)
    assert aggregate.publication_state == Article.PublicationState.SCHEDULED
    assert aggregate.scheduled_revision_id == article.revision_id
    assert aggregate.scheduled_for == scheduled.scheduled_for

    another = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(aggregate.working_revision.section_id, "过去时间"),
        capacity_check=lambda: None,
    )
    with pytest.raises(PublicationCommandError) as captured:
        _schedule(admin, another, datetime(2026, 7, 23, 7, 59), now)
    assert captured.value.code == "content.schedule_time_invalid.v1"


def test_scheduled_revision_does_not_drift_when_working_revision_changes() -> None:
    admin, section, article = _setup("locked-revision")
    now = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)
    schedule = _schedule(admin, article, datetime(2026, 7, 23, 10, 0), now)
    edited = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(section.section_id, "后来编辑"),
        capacity_check=lambda: None,
    )

    outcome = publish_scheduled_article(
        article_id=article.article_id,
        scheduled_revision_id=article.revision_id,
        clock=FrozenClock(schedule.scheduled_for),
    )

    aggregate = Article.objects.get(pk=article.article_id)
    assert outcome.outcome == "published"
    assert aggregate.working_revision_id == edited.revision_id
    assert aggregate.published_revision_id == article.revision_id
    assert published_revision(article.article_id).body_markdown == "排期版本"


def test_cancel_and_execution_business_rechecks_are_safe() -> None:
    admin, section, article = _setup("cancel")
    now = datetime(2026, 7, 23, 2, 0, tzinfo=UTC)
    schedule = _schedule(admin, article, datetime(2026, 7, 23, 11, 0), now)
    cancelled = cancel_schedule(
        actor_id=admin.id,
        article_id=article.article_id,
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )
    assert cancelled.cancelled is True
    assert (
        publish_scheduled_article(
            article_id=article.article_id,
            scheduled_revision_id=article.revision_id,
            clock=FrozenClock(schedule.scheduled_for),
        ).outcome
        == "stale"
    )

    disabled = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, "禁用作者"),
        capacity_check=lambda: None,
    )
    disabled_schedule = _schedule(admin, disabled, datetime(2026, 7, 23, 11, 30), now)
    invalid = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section.section_id, "分区失效"),
        capacity_check=lambda: None,
    )
    invalid_schedule = _schedule(admin, invalid, datetime(2026, 7, 23, 11, 45), now)
    delete_section(
        actor_id=admin.id,
        section_id=section.section_id,
        **_context(),
    )
    invalid_result = publish_scheduled_article(
        article_id=invalid.article_id,
        scheduled_revision_id=invalid.revision_id,
        clock=FrozenClock(invalid_schedule.scheduled_for),
    )
    assert invalid_result.outcome == "cancelled_invalid"
    admin.status = "DISABLED"
    admin.save(update_fields=("status", "updated_at"))
    result = publish_scheduled_article(
        article_id=disabled.article_id,
        scheduled_revision_id=disabled.revision_id,
        clock=FrozenClock(disabled_schedule.scheduled_for),
    )
    assert result.outcome == "cancelled_author"
    aggregate = Article.objects.get(pk=disabled.article_id)
    assert aggregate.publication_state == Article.PublicationState.DRAFT
    assert aggregate.scheduled_revision_id is None


def test_two_workers_publish_once_and_blocker_cancels() -> None:
    admin, _, article = _setup("workers")
    now = datetime(2026, 7, 23, 3, 0, tzinfo=UTC)
    schedule = _schedule(admin, article, datetime(2026, 7, 23, 12, 0), now)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def publish() -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            result = publish_scheduled_article(
                article_id=article.article_id,
                scheduled_revision_id=article.revision_id,
                clock=FrozenClock(schedule.scheduled_for),
            )
            outcomes.append(result.outcome)
        finally:
            close_old_connections()

    workers = [threading.Thread(target=publish), threading.Thread(target=publish)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert sorted(outcomes) == ["published", "stale"]
    outbox_model = apps.get_model("core", "OutboxEvent")
    assert outbox_model.objects.filter(event_type="article.published.v1").count() == 1

    blocked = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(
            Article.objects.get(pk=article.article_id).published_revision.section_id,
            "被遮罩",
        ),
        capacity_check=lambda: None,
    )
    blocked_schedule = _schedule(admin, blocked, datetime(2026, 7, 23, 12, 30), now)
    result = publish_scheduled_article(
        article_id=blocked.article_id,
        scheduled_revision_id=blocked.revision_id,
        publication_blocker=lambda _article_id: True,
        clock=FrozenClock(blocked_schedule.scheduled_for),
    )
    assert result.outcome == "cancelled_blocked"


def test_celery_entry_records_taskrun_and_beat_schedule() -> None:
    admin, _, article = _setup("taskrun")
    actual_now = datetime.now(UTC)
    scheduled_local = actual_now.astimezone(SHANGHAI).replace(tzinfo=None)
    _schedule(
        admin,
        article,
        scheduled_local,
        actual_now - timedelta(minutes=1),
    )

    response = publish_scheduled_article_task.apply(
        args=(article.article_id, article.revision_id),
        task_id=str(uuid4()),
    ).get()

    task_run = apps.get_model("operations", "TaskRun")
    run = task_run.objects.get(
        task_name="apps.content.publish_scheduled_article",
        idempotency_key=(
            f"article:{article.article_id}:schedule:{article.revision_id}"
        ),
    )
    assert response["status"] == "published"
    assert run.status == "succeeded"
    assert (
        settings.CELERY_BEAT_SCHEDULE["content-publish-scheduled"]["schedule"] == 60.0
    )


def test_scheduled_task_retries_twice_then_succeeds(monkeypatch) -> None:
    admin, _, article = _setup("task-retry")
    actual_now = datetime.now(UTC)
    scheduled_local = actual_now.astimezone(SHANGHAI).replace(tzinfo=None)
    _schedule(
        admin,
        article,
        scheduled_local,
        actual_now - timedelta(minutes=1),
    )
    original = publication_tasks._scheduled_service
    attempts = 0

    def flaky_service(business_object: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableTaskError("content.schedule_transient.v1")
        return original(business_object)

    monkeypatch.setattr(publication_tasks, "_scheduled_service", flaky_service)
    task_run = apps.get_model("operations", "TaskRun")
    key = f"article:{article.article_id}:schedule:{article.revision_id}"
    for expected_attempt in (1, 2):
        with pytest.raises(Retry):
            publish_scheduled_article_task.apply(
                args=(article.article_id, article.revision_id),
                task_id=str(uuid4()),
                throw=True,
            )
        run = task_run.objects.get(idempotency_key=key)
        assert run.attempt == expected_attempt
        assert run.status == "retry_wait"
        task_run.objects.filter(pk=run.pk).update(
            available_at=timezone.now() - timedelta(seconds=1)
        )

    result = publish_scheduled_article_task.apply(
        args=(article.article_id, article.revision_id),
        task_id=str(uuid4()),
        throw=False,
    )
    assert result.state == "SUCCESS"
    assert result.get()["status"] == "published"
    run = task_run.objects.get(idempotency_key=key)
    assert run.attempt == 3
    assert run.status == "succeeded"
