from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.db import OperationalError

from apps.core.events.models import OutboxEvent
from apps.core.events.outbox import envelope_from_model
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.notifications.consumers.opportunities import consume_opportunity_notification
from apps.notifications.models import Notification
from apps.notifications.templates_registry import render_notification
from apps.operations.models import TaskRun, TaskRunStatus
from apps.opportunities.models import (
    OpportunityCheckRun,
    OpportunityCheckRunSource,
    OpportunitySource,
)
from apps.opportunities.services.check_runs import request_scheduled_full_check
from apps.opportunities.services.recovery import (
    LEASE_EXPIRED_ERROR,
    RUN_CHECK_TASK_NAME,
    SOURCE_TIMEOUT_WARNING,
    recover_expired_check_runs,
)
from apps.opportunities.services.run_execution import execute_check_run
from apps.opportunities.tasks import (
    RECOVER_CHECK_LEASES_TASK_NAME,
    recover_check_leases_task,
)

pytestmark = pytest.mark.django_db(transaction=True)

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)


def _source(position: int = 1) -> OpportunitySource:
    return OpportunitySource.objects.create(
        company_name=f"恢复测试来源 {position}",
        normalized_company_name=f"recovery-source-{position}-{uuid4()}",
        source_type=OpportunitySource.SourceType.CAMPUS,
        official_url=f"https://recovery-{position}-{uuid4()}.example.com/jobs",
        adapter_key="example-v1",
        enabled=True,
        publicly_visible=True,
    )


def _running_run(*, attempt: int = 1, sources: int = 1):
    rows = [_source(position) for position in range(1, sources + 1)]
    run = OpportunityCheckRun.objects.create(
        kind=OpportunityCheckRun.Kind.FULL,
        trigger="SCHEDULED",
        state=OpportunityCheckRun.State.RUNNING,
        current_source=rows[0],
        total_sources=len(rows),
        started_at=NOW - timedelta(hours=2),
    )
    items = [
        OpportunityCheckRunSource.objects.create(
            run=run,
            source=source,
            position=position,
            state=(
                OpportunityCheckRunSource.State.RUNNING
                if position == 1
                else OpportunityCheckRunSource.State.PENDING
            ),
            started_at=NOW - timedelta(hours=1) if position == 1 else None,
        )
        for position, source in enumerate(rows, start=1)
    ]
    task_run = TaskRun.objects.create(
        run_id=new_ulid(),
        task_name=RUN_CHECK_TASK_NAME,
        business_object=f"opportunity-run:{run.id}",
        idempotency_key=f"opportunity-run:{run.id}",
        celery_id=str(uuid4()),
        trace_code=new_trace_code(),
        status=TaskRunStatus.RUNNING,
        attempt=attempt,
        scheduled_at=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=2),
        started_at=NOW - timedelta(hours=2),
        heartbeat_at=NOW - timedelta(minutes=10),
        lease_token=uuid4(),
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    run.task_run_id = task_run.run_id
    run.save(update_fields=("task_run_id", "updated_at"))
    return run, items, task_run


def test_database_disconnect_releases_source_without_masking_original(
    monkeypatch,
) -> None:
    run, items, _task_run = _running_run()
    OpportunityCheckRun.objects.filter(pk=run.id).update(
        state=OpportunityCheckRun.State.PENDING,
        current_source=None,
        started_at=None,
    )
    OpportunityCheckRunSource.objects.filter(pk=items[0].id).update(
        state=OpportunityCheckRunSource.State.PENDING,
        started_at=None,
    )
    original = OperationalError("server closed the connection unexpectedly")
    monkeypatch.setattr(
        "apps.opportunities.services.run_execution.run_source_check",
        lambda **_kwargs: (_ for _ in ()).throw(original),
    )

    with pytest.raises(OperationalError) as failed:
        execute_check_run(run.id, lambda: None, clock=FrozenClock(NOW))

    assert failed.value is original
    items[0].refresh_from_db()
    run.refresh_from_db()
    assert items[0].state == OpportunityCheckRunSource.State.PENDING
    assert items[0].safe_error_code == "opportunities.source_interrupted.v1"
    assert run.current_source_id is None


def test_release_failure_does_not_replace_database_error(monkeypatch) -> None:
    run, items, _task_run = _running_run()
    OpportunityCheckRun.objects.filter(pk=run.id).update(
        state=OpportunityCheckRun.State.PENDING,
        current_source=None,
        started_at=None,
    )
    OpportunityCheckRunSource.objects.filter(pk=items[0].id).update(
        state=OpportunityCheckRunSource.State.PENDING,
        started_at=None,
    )
    original = OperationalError("server closed the connection unexpectedly")
    monkeypatch.setattr(
        "apps.opportunities.services.run_execution.run_source_check",
        lambda **_kwargs: (_ for _ in ()).throw(original),
    )
    monkeypatch.setattr(
        "apps.opportunities.services.run_execution._release_source_item",
        lambda _item_id: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    with pytest.raises(OperationalError) as failed:
        execute_check_run(run.id, lambda: None, clock=FrozenClock(NOW))

    assert failed.value is original


def test_expired_worker_lease_requeues_source_and_redispatches_when_due() -> None:
    run, items, task_run = _running_run()
    dispatched = []

    recovered = recover_expired_check_runs(
        dispatcher=dispatched.append,
        clock=FrozenClock(NOW),
    )

    task_run.refresh_from_db()
    items[0].refresh_from_db()
    run.refresh_from_db()
    assert recovered.recovered == 1
    assert recovered.redispatched == 0
    assert task_run.status == TaskRunStatus.RETRY_WAIT
    assert items[0].state == OpportunityCheckRunSource.State.PENDING
    assert items[0].safe_error_code == LEASE_EXPIRED_ERROR
    assert run.current_source_id is None

    due = recover_expired_check_runs(
        dispatcher=dispatched.append,
        clock=FrozenClock(NOW + timedelta(seconds=60)),
    )
    assert due.recovered == 0
    assert due.redispatched == 1
    assert dispatched == [run.id]


def test_expired_worker_lease_records_admin_stalled_event() -> None:
    run, items, task_run = _running_run()
    dispatched = []

    recover_expired_check_runs(
        dispatcher=dispatched.append,
        clock=FrozenClock(NOW),
    )

    event = OutboxEvent.objects.get(event_type="opportunity.check_stalled.v1")
    assert event.aggregate_id == run.id
    assert event.trace_code == task_run.trace_code
    assert event.payload == {
        "run_id": run.id,
        "source_name": items[0].source.company_name,
        "source_position": 1,
        "reason": "LEASE_EXPIRED",
        "attempt": 1,
        "final_failed": False,
        "max_duration_seconds": 0,
    }
    rendered = render_notification("opportunity.check_stalled.v1", event.payload)
    assert rendered.title == "招聘检查租约已过期"
    assert "将自动重试" in rendered.message


def test_expired_worker_lease_delivers_admin_notification() -> None:
    from tests.fixtures.accounts import bootstrap_test_administrator

    administrator = bootstrap_test_administrator()
    run, _items, _task_run = _running_run()
    recover_expired_check_runs(dispatcher=lambda _run_id: None, clock=FrozenClock(NOW))
    event = OutboxEvent.objects.get(event_type="opportunity.check_stalled.v1")

    first = consume_opportunity_notification(
        envelope_from_model(event),
        administrator_id_provider=lambda: administrator.id,
    )
    second = consume_opportunity_notification(
        envelope_from_model(event),
        administrator_id_provider=lambda: administrator.id,
    )

    assert first.outcome.value == "processed"
    assert second.outcome.value == "already_processed"
    assert (
        Notification.objects.filter(
            template_key="opportunity.check_stalled.v1",
            target_id=run.id,
        ).count()
        == 1
    )


def test_source_timeout_warning_is_persisted_once() -> None:
    run, items, task_run = _running_run()
    task_run.lease_expires_at = NOW + timedelta(hours=1)
    task_run.save(update_fields=("lease_expires_at", "updated_at"))
    source = items[0].source
    source.max_duration_seconds = 60
    source.save(update_fields=("max_duration_seconds", "updated_at"))

    first = recover_expired_check_runs(
        dispatcher=lambda _run_id: None, clock=FrozenClock(NOW)
    )
    items[0].refresh_from_db()
    assert first.stalled == 1
    assert items[0].safe_error_code == SOURCE_TIMEOUT_WARNING
    assert (
        OutboxEvent.objects.filter(event_type="opportunity.check_stalled.v1").count()
        == 1
    )

    second = recover_expired_check_runs(
        dispatcher=lambda _run_id: None, clock=FrozenClock(NOW)
    )
    assert second.stalled == 0
    assert (
        OutboxEvent.objects.filter(event_type="opportunity.check_stalled.v1").count()
        == 1
    )


def test_recovery_retries_domain_reconciliation_after_database_disconnect(monkeypatch):
    import apps.opportunities.services.recovery as recovery_service

    _run, items, task_run = _running_run()
    original = recovery_service._reconcile_recovered_task
    calls = 0

    def flaky(task, final_failed, *, now):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("server closed the connection unexpectedly")
        return original(task, final_failed, now=now)

    monkeypatch.setattr(recovery_service, "_reconcile_recovered_task", flaky)
    result = recover_expired_check_runs(
        dispatcher=lambda _run_id: None,
        clock=FrozenClock(NOW),
    )

    task_run.refresh_from_db()
    items[0].refresh_from_db()
    assert result.recovered == 1
    assert calls == 2
    assert task_run.status == TaskRunStatus.RETRY_WAIT
    assert items[0].state == OpportunityCheckRunSource.State.PENDING


def test_terminal_task_failure_closes_orphaned_active_run() -> None:
    run, items, task_run = _running_run(sources=2)
    task_run.status = TaskRunStatus.FINAL_FAILED
    task_run.completed_at = NOW
    task_run.last_error_code = "operations.task_unexpected.v1"
    task_run.lease_token = None
    task_run.lease_expires_at = None
    task_run.save(
        update_fields=(
            "status",
            "completed_at",
            "last_error_code",
            "lease_token",
            "lease_expires_at",
            "updated_at",
        )
    )

    result = recover_expired_check_runs(
        dispatcher=lambda _run_id: None,
        clock=FrozenClock(NOW),
    )

    run.refresh_from_db()
    assert result.reconciled == 1
    assert run.state == OpportunityCheckRun.State.FAILED
    assert run.current_source_id is None
    assert set(run.source_runs.values_list("state", flat=True)) == {
        OpportunityCheckRunSource.State.FAILED
    }
    assert not OpportunityCheckRun.objects.filter(
        state__in=(
            OpportunityCheckRun.State.PENDING,
            OpportunityCheckRun.State.RUNNING,
            OpportunityCheckRun.State.CANCEL_REQUESTED,
        )
    ).exists()


def test_third_expired_lease_finishes_old_run_and_next_schedule_creates_new() -> None:
    old_run, items, task_run = _running_run(attempt=3, sources=2)
    dispatched = []

    result = recover_expired_check_runs(
        dispatcher=dispatched.append,
        clock=FrozenClock(NOW),
    )

    task_run.refresh_from_db()
    old_run.refresh_from_db()
    items[0].refresh_from_db()
    items[1].refresh_from_db()
    assert result.recovered == 1
    assert task_run.status == TaskRunStatus.FINAL_FAILED
    assert old_run.state == OpportunityCheckRun.State.FAILED
    assert items[0].state == OpportunityCheckRunSource.State.FAILED
    assert items[1].state == OpportunityCheckRunSource.State.NOT_EXECUTED
    assert OutboxEvent.objects.filter(event_type="task.final_failed.v1").count() == 1

    scheduled = request_scheduled_full_check(dispatcher=dispatched.append)
    assert scheduled.reused is False
    assert scheduled.run_id != old_run.id
    assert dispatched == [scheduled.run_id]


def test_recovery_is_a_real_minute_celery_task() -> None:
    schedule = settings.CELERY_BEAT_SCHEDULE["opportunities-recover-check-leases"]
    assert schedule["task"] == RECOVER_CHECK_LEASES_TASK_NAME
    assert schedule["schedule"] == 60.0
    assert recover_check_leases_task.name == RECOVER_CHECK_LEASES_TASK_NAME
