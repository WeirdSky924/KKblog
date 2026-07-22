from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import connection, connections, transaction

from apps.core.events.models import OutboxEvent
from apps.core.time.clock import FrozenClock
from apps.operations.models import TaskRun, TaskRunStatus
from apps.operations.services.tasks import (
    StartOutcome,
    TaskFinalFailed,
    TaskRetryScheduled,
    claim_task,
    execute_tracked_task,
    heartbeat_task,
    recover_expired_task_leases,
    retry_delay_seconds,
)
from config.runtime_tasks import smoke

BASE_TIME = datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
TASK_NAME = "tests.operations.example"
PAYLOAD_ID = "article:01K0QZ3X8VK4M8K6G5YH2T1R9P"
IDEMPOTENCY_KEY = "article:01K0QZ3X8VK4M8K6G5YH2T1R9P:publish"


@pytest.fixture(autouse=True)
def require_postgresql() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("OBS-006 requires isolated PostgreSQL")


def _celery_id() -> str:
    return str(uuid4())


def _execute(service, *, clock: FrozenClock, celery_id: str | None = None):
    return execute_tracked_task(
        task_name=TASK_NAME,
        business_object=PAYLOAD_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        celery_id=celery_id or _celery_id(),
        service=service,
        lease_seconds=30,
        jitter=lambda base: 0,
        clock=clock,
    )


@pytest.mark.django_db(transaction=True)
def test_first_success_and_duplicate_call_service_once() -> None:
    calls = []

    def service(business_object: str) -> str:
        calls.append(business_object)
        return f"result:{business_object.rsplit(':', 1)[-1]}"

    first = _execute(service, clock=FrozenClock(BASE_TIME))
    duplicate = _execute(
        service,
        clock=FrozenClock(BASE_TIME + timedelta(minutes=1)),
    )

    task_run = TaskRun.objects.get()
    assert first.outcome == StartOutcome.SUCCEEDED
    assert duplicate.outcome == StartOutcome.ALREADY_SUCCEEDED
    assert calls == [PAYLOAD_ID]
    assert task_run.status == TaskRunStatus.SUCCEEDED
    assert task_run.attempt == 1
    assert task_run.scheduled_at == BASE_TIME
    assert task_run.started_at == BASE_TIME
    assert task_run.completed_at == BASE_TIME
    assert task_run.lease_token is None
    assert task_run.result_ref == first.result_ref == duplicate.result_ref


@pytest.mark.django_db(transaction=True)
def test_two_failures_then_third_attempt_succeeds() -> None:
    outcomes = iter((RuntimeError("private-1"), RuntimeError("private-2"), "done"))

    def service(business_object: str) -> str:
        del business_object
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with pytest.raises(TaskRetryScheduled) as first:
        _execute(service, clock=FrozenClock(BASE_TIME))
    assert first.value.countdown == 60

    with pytest.raises(TaskRetryScheduled) as second:
        _execute(
            service,
            clock=FrozenClock(BASE_TIME + timedelta(seconds=60)),
        )
    assert second.value.countdown == 300

    result = _execute(
        service,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=360)),
    )
    task_run = TaskRun.objects.get()
    assert result.outcome == StartOutcome.SUCCEEDED
    assert task_run.status == TaskRunStatus.SUCCEEDED
    assert task_run.attempt == 3
    assert task_run.last_error_code == ""
    assert task_run.lease_token is None


@pytest.mark.django_db(transaction=True)
def test_three_failures_write_one_safe_final_failure_fact() -> None:
    def failing_service(business_object: str) -> str:
        del business_object
        raise RuntimeError("postgresql://owner:private@host/database")

    for moment, countdown in (
        (BASE_TIME, 60),
        (BASE_TIME + timedelta(seconds=60), 300),
    ):
        with pytest.raises(TaskRetryScheduled) as captured:
            _execute(failing_service, clock=FrozenClock(moment))
        assert captured.value.countdown == countdown

    with pytest.raises(TaskFinalFailed) as final:
        _execute(
            failing_service,
            clock=FrozenClock(BASE_TIME + timedelta(seconds=360)),
        )
    with pytest.raises(TaskFinalFailed):
        _execute(
            failing_service,
            clock=FrozenClock(BASE_TIME + timedelta(seconds=361)),
        )

    task_run = TaskRun.objects.get()
    event = OutboxEvent.objects.get(event_type="task.final_failed.v1")
    assert final.value.error_code == "operations.task_unexpected.v1"
    assert task_run.status == TaskRunStatus.FINAL_FAILED
    assert task_run.attempt == 3
    assert task_run.completed_at == BASE_TIME + timedelta(seconds=360)
    assert task_run.lease_token is None
    assert event.aggregate_type == "task_run"
    assert event.aggregate_id == task_run.run_id
    assert event.payload == {
        "task_name": TASK_NAME,
        "business_object": PAYLOAD_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "attempt": 3,
        "error_code": "operations.task_unexpected.v1",
    }
    serialized = str(task_run.last_error_code) + str(event.payload)
    assert "private" not in serialized
    assert "postgresql://" not in serialized
    assert OutboxEvent.objects.filter(event_type="task.final_failed.v1").count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_workers_cannot_claim_the_same_idempotency_key() -> None:
    barrier = Barrier(2)

    def worker() -> StartOutcome:
        connections.close_all()
        barrier.wait(timeout=5)
        try:
            result = claim_task(
                task_name=TASK_NAME,
                business_object=PAYLOAD_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                celery_id=_celery_id(),
                lease_seconds=30,
                clock=FrozenClock(BASE_TIME),
            )
            return result.outcome
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: worker(), range(2)))

    assert sorted(outcomes) == sorted((StartOutcome.CLAIMED, StartOutcome.BUSY))
    task_run = TaskRun.objects.get()
    assert task_run.status == TaskRunStatus.RUNNING
    assert task_run.attempt == 1


@pytest.mark.django_db(transaction=True)
def test_outer_transaction_rollback_removes_claim() -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        claim_task(
            task_name=TASK_NAME,
            business_object=PAYLOAD_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            celery_id=_celery_id(),
            clock=FrozenClock(BASE_TIME),
        )
        raise RuntimeError("simulated pre-commit crash")

    assert TaskRun.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_post_commit_hard_crash_is_recovered_after_lease() -> None:
    class ProcessCrash(BaseException):
        pass

    def crashing_service(business_object: str) -> str:
        del business_object
        raise ProcessCrash

    with pytest.raises(ProcessCrash):
        _execute(crashing_service, clock=FrozenClock(BASE_TIME))
    task_run = TaskRun.objects.get()
    assert task_run.status == TaskRunStatus.RUNNING
    assert task_run.lease_expires_at == BASE_TIME + timedelta(seconds=30)

    assert (
        recover_expired_task_leases(
            batch_size=10,
            clock=FrozenClock(BASE_TIME + timedelta(seconds=31)),
            jitter=lambda base: 0,
        )
        == 1
    )
    task_run.refresh_from_db()
    assert task_run.status == TaskRunStatus.RETRY_WAIT
    assert task_run.available_at == BASE_TIME + timedelta(seconds=91)
    assert task_run.lease_token is None

    result = _execute(
        lambda business_object: f"recovered:{business_object}",
        clock=FrozenClock(BASE_TIME + timedelta(seconds=91)),
    )
    task_run.refresh_from_db()
    assert result.outcome == StartOutcome.SUCCEEDED
    assert task_run.status == TaskRunStatus.SUCCEEDED
    assert task_run.attempt == 2


@pytest.mark.django_db(transaction=True)
def test_expired_third_attempt_becomes_final_failed_once() -> None:
    claim_times = (
        BASE_TIME,
        BASE_TIME + timedelta(seconds=71),
        BASE_TIME + timedelta(seconds=382),
    )
    recovery_times = (
        BASE_TIME + timedelta(seconds=11),
        BASE_TIME + timedelta(seconds=82),
        BASE_TIME + timedelta(seconds=393),
    )
    for index, (claim_time, recovery_time) in enumerate(
        zip(claim_times, recovery_times, strict=True),
        start=1,
    ):
        claimed = claim_task(
            task_name=TASK_NAME,
            business_object=PAYLOAD_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            celery_id=_celery_id(),
            lease_seconds=10,
            clock=FrozenClock(claim_time),
            jitter=lambda base: 0,
        )
        assert claimed.outcome == StartOutcome.CLAIMED
        assert claimed.claim is not None
        assert claimed.claim.attempt == index
        assert (
            recover_expired_task_leases(
                batch_size=10,
                clock=FrozenClock(recovery_time),
                jitter=lambda base: 0,
            )
            == 1
        )

    task_run = TaskRun.objects.get()
    assert task_run.status == TaskRunStatus.FINAL_FAILED
    assert task_run.attempt == 3
    assert task_run.lease_token is None
    assert task_run.last_error_code == "operations.task_lease_expired.v1"
    assert OutboxEvent.objects.filter(event_type="task.final_failed.v1").count() == 1
    assert (
        recover_expired_task_leases(
            batch_size=10,
            clock=FrozenClock(BASE_TIME + timedelta(seconds=500)),
        )
        == 0
    )
    assert OutboxEvent.objects.filter(event_type="task.final_failed.v1").count() == 1


@pytest.mark.django_db(transaction=True)
def test_service_rereads_business_object_on_each_attempt() -> None:
    source = {PAYLOAD_ID: "old"}
    observed = []

    def service(business_object: str) -> str:
        observed.append(source[business_object])
        if source[business_object] == "old":
            raise RuntimeError("retry after object changes")
        return source[business_object]

    with pytest.raises(TaskRetryScheduled):
        _execute(service, clock=FrozenClock(BASE_TIME))
    source[PAYLOAD_ID] = "new"
    result = _execute(
        service,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=60)),
    )

    assert observed == ["old", "new"]
    assert result.result_ref == "new"


@pytest.mark.django_db(transaction=True)
def test_heartbeat_requires_current_lease_token() -> None:
    claimed = claim_task(
        task_name=TASK_NAME,
        business_object=PAYLOAD_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        celery_id=_celery_id(),
        lease_seconds=30,
        clock=FrozenClock(BASE_TIME),
    )
    assert claimed.claim is not None

    renewed = heartbeat_task(
        claimed.claim,
        lease_seconds=45,
        clock=FrozenClock(BASE_TIME + timedelta(seconds=10)),
    )
    task_run = TaskRun.objects.get()
    assert renewed is True
    assert task_run.heartbeat_at == BASE_TIME + timedelta(seconds=10)
    assert task_run.lease_expires_at == BASE_TIME + timedelta(seconds=55)


@pytest.mark.django_db(transaction=True)
def test_existing_celery_smoke_entry_is_tracked_and_idempotent() -> None:
    probe_id = _celery_id()
    first = smoke.apply(args=(probe_id,), task_id=_celery_id()).get()
    duplicate = smoke.apply(args=(probe_id,), task_id=_celery_id()).get()

    task_run = TaskRun.objects.get(task_name="config.runtime_tasks.smoke")
    assert first == duplicate == {"probe_id": probe_id, "status": "ok"}
    assert task_run.business_object == probe_id
    assert task_run.idempotency_key == f"runtime-smoke:{probe_id}"
    assert task_run.status == TaskRunStatus.SUCCEEDED
    assert task_run.attempt == 1


def test_retry_policy_is_increasing_and_adds_injected_jitter() -> None:
    assert [
        retry_delay_seconds(attempt, jitter=lambda base: base // 10)
        for attempt in (1, 2, 3)
    ] == [66, 330, 1980]
