from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from math import ceil
from uuid import UUID

from django.db import transaction

from apps.core.events.outbox import enqueue_event
from apps.core.ids import new_ulid, new_uuid
from apps.core.observability.context import (
    bind_trace_code,
    current_trace_code,
    reset_trace_code,
)
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import Clock, SystemClock
from apps.operations.events import TASK_FINAL_FAILED
from apps.operations.models import TaskRun, TaskRunStatus

MAX_ATTEMPTS = 3
BASE_RETRY_DELAYS_SECONDS = (60, 300, 1_800)
DEFAULT_LEASE_SECONDS = 300
TASK_UNEXPECTED_ERROR = "operations.task_unexpected.v1"
TASK_LEASE_EXPIRED = "operations.task_lease_expired.v1"
TASK_BUSY = "operations.task_busy.v1"

_TASK_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_.-]{0,254}\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")

Jitter = Callable[[int], int]
TaskService = Callable[[str], str | None]
HeartbeatTaskService = Callable[[str, Callable[[], None]], str | None]


class StartOutcome(StrEnum):
    CLAIMED = "claimed"
    BUSY = "busy"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    ALREADY_SUCCEEDED = "already_succeeded"
    FINAL_FAILED = "final_failed"


class TaskRetryScheduled(RuntimeError):
    def __init__(self, *, countdown: int, error_code: str) -> None:
        self.countdown = countdown
        self.error_code = error_code
        super().__init__(error_code)


class TaskFinalFailed(RuntimeError):
    def __init__(self, *, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class TaskLeaseLost(RuntimeError):
    """The worker no longer owns the lease and must not publish success."""


class RetryableTaskError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = _validate_error_code(error_code)
        super().__init__(self.error_code)


@dataclass(frozen=True, slots=True)
class TaskClaim:
    run_id: str
    lease_token: UUID
    attempt: int
    trace_code: str


@dataclass(frozen=True, slots=True)
class TaskStartResult:
    outcome: StartOutcome
    claim: TaskClaim | None = None
    retry_after_seconds: int = 0
    result_ref: str = ""
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class TaskFailureResult:
    outcome: StartOutcome
    retry_after_seconds: int = 0


def _validate_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {field_name}")
    return value


def _validate_task_name(value: str) -> str:
    if not isinstance(value, str) or not _TASK_NAME.fullmatch(value):
        raise ValueError("Invalid task_name")
    return value


def _validate_error_code(value: str) -> str:
    if not isinstance(value, str) or not _ERROR_CODE.fullmatch(value):
        raise ValueError("Invalid error_code")
    return value


def _validate_celery_id(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid celery_id") from None


def _validate_lease_seconds(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 86_400
    ):
        raise ValueError("Invalid lease_seconds")
    return value


def _jitter_value(base_seconds: int) -> int:
    return secrets.randbelow(max(1, base_seconds // 10 + 1))


def retry_delay_seconds(attempt: int, *, jitter: Jitter | None = None) -> int:
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        raise ValueError("Invalid attempt")
    if not 1 <= attempt <= len(BASE_RETRY_DELAYS_SECONDS):
        raise ValueError("Invalid attempt")
    base = BASE_RETRY_DELAYS_SECONDS[attempt - 1]
    offset = (jitter or _jitter_value)(base)
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or not 0 <= offset <= base // 10
    ):
        raise ValueError("Invalid retry jitter")
    return base + offset


def _retry_after(run: TaskRun, now) -> int:
    if run.available_at <= now:
        return 0
    return max(1, ceil((run.available_at - now).total_seconds()))


def _task_claim(run: TaskRun) -> TaskClaim:
    if run.lease_token is None:
        raise RuntimeError("Task run has no active lease")
    return TaskClaim(
        run_id=run.run_id,
        lease_token=run.lease_token,
        attempt=run.attempt,
        trace_code=run.trace_code,
    )


def _final_failure_locked(
    run: TaskRun,
    *,
    error_code: str,
    now,
    clock: Clock,
) -> None:
    run.status = TaskRunStatus.FINAL_FAILED
    run.completed_at = now
    run.last_error_code = error_code
    run.lease_token = None
    run.lease_expires_at = None
    run.save(
        update_fields=(
            "status",
            "completed_at",
            "last_error_code",
            "lease_token",
            "lease_expires_at",
            "updated_at",
        )
    )
    enqueue_event(
        TASK_FINAL_FAILED,
        aggregate_type="task_run",
        aggregate_id=run.run_id,
        payload={
            "task_name": run.task_name,
            "business_object": run.business_object,
            "idempotency_key": run.idempotency_key,
            "attempt": run.attempt,
            "error_code": error_code,
        },
        trace_code=run.trace_code,
        clock=clock,
    )


def _release_expired_locked(
    run: TaskRun,
    *,
    now,
    clock: Clock,
    jitter: Jitter | None,
) -> bool:
    if run.status != TaskRunStatus.RUNNING or run.lease_expires_at is None:
        return False
    if run.lease_expires_at > now:
        return False
    run.last_error_code = TASK_LEASE_EXPIRED
    run.heartbeat_at = now
    run.lease_token = None
    run.lease_expires_at = None
    if run.attempt >= MAX_ATTEMPTS:
        _final_failure_locked(run, error_code=TASK_LEASE_EXPIRED, now=now, clock=clock)
        return True
    run.status = TaskRunStatus.RETRY_WAIT
    run.available_at = now + timedelta(
        seconds=retry_delay_seconds(run.attempt, jitter=jitter)
    )
    run.save(
        update_fields=(
            "status",
            "available_at",
            "heartbeat_at",
            "last_error_code",
            "lease_token",
            "lease_expires_at",
            "updated_at",
        )
    )
    return False


def claim_task(
    *,
    task_name: str,
    business_object: str,
    idempotency_key: str,
    celery_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    clock: Clock | None = None,
    jitter: Jitter | None = None,
) -> TaskStartResult:
    task_name = _validate_task_name(task_name)
    business_object = _validate_identifier(business_object, "business_object")
    idempotency_key = _validate_identifier(idempotency_key, "idempotency_key")
    celery_id = _validate_celery_id(celery_id)
    lease_seconds = _validate_lease_seconds(lease_seconds)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        run, created = TaskRun.objects.select_for_update().get_or_create(
            task_name=task_name,
            idempotency_key=idempotency_key,
            defaults={
                "run_id": new_ulid(),
                "business_object": business_object,
                "celery_id": celery_id,
                "trace_code": current_trace_code() or new_trace_code(),
                "scheduled_at": now,
                "available_at": now,
            },
        )
        if not created and run.business_object != business_object:
            raise ValueError("Task idempotency key targets another object")
        if run.status == TaskRunStatus.SUCCEEDED:
            return TaskStartResult(
                StartOutcome.ALREADY_SUCCEEDED,
                result_ref=run.result_ref,
            )
        if run.status == TaskRunStatus.FINAL_FAILED:
            return TaskStartResult(
                StartOutcome.FINAL_FAILED,
                error_code=run.last_error_code,
            )
        if run.status == TaskRunStatus.RUNNING:
            if _release_expired_locked(run, now=now, clock=active_clock, jitter=jitter):
                return TaskStartResult(
                    StartOutcome.FINAL_FAILED,
                    error_code=TASK_LEASE_EXPIRED,
                )
            if run.status == TaskRunStatus.RUNNING:
                return TaskStartResult(
                    StartOutcome.BUSY,
                    retry_after_seconds=max(1, _retry_after(run, now)),
                )
        if run.available_at > now:
            return TaskStartResult(
                StartOutcome.BUSY,
                retry_after_seconds=_retry_after(run, now),
            )

        lease_token = new_uuid()
        run.status = TaskRunStatus.RUNNING
        run.attempt += 1
        run.celery_id = celery_id
        run.started_at = run.started_at or now
        run.heartbeat_at = now
        run.lease_token = lease_token
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        run.save(
            update_fields=(
                "status",
                "attempt",
                "celery_id",
                "started_at",
                "heartbeat_at",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            )
        )
        return TaskStartResult(StartOutcome.CLAIMED, claim=_task_claim(run))


def heartbeat_task(
    claim: TaskClaim,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    clock: Clock | None = None,
) -> bool:
    if not isinstance(claim, TaskClaim):
        raise TypeError("claim must be a TaskClaim")
    lease_seconds = _validate_lease_seconds(lease_seconds)
    now = (clock or SystemClock()).now()
    updated = TaskRun.objects.filter(
        run_id=claim.run_id,
        status=TaskRunStatus.RUNNING,
        lease_token=claim.lease_token,
        lease_expires_at__gt=now,
    ).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )
    return updated == 1


def _result_ref(value: str | None) -> str:
    if value is None or value == "":
        return ""
    return _validate_identifier(value, "result_ref")


def complete_task(
    claim: TaskClaim,
    *,
    result_ref: str | None,
    clock: Clock | None = None,
) -> bool:
    if not isinstance(claim, TaskClaim):
        raise TypeError("claim must be a TaskClaim")
    normalized_result = _result_ref(result_ref)
    now = (clock or SystemClock()).now()
    with transaction.atomic():
        run = TaskRun.objects.select_for_update().get(run_id=claim.run_id)
        if run.status != TaskRunStatus.RUNNING or run.lease_token != claim.lease_token:
            return False
        run.status = TaskRunStatus.SUCCEEDED
        run.completed_at = now
        run.result_ref = normalized_result
        run.last_error_code = ""
        run.heartbeat_at = now
        run.lease_token = None
        run.lease_expires_at = None
        run.save(
            update_fields=(
                "status",
                "completed_at",
                "result_ref",
                "last_error_code",
                "heartbeat_at",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            )
        )
    return True


def fail_task(
    claim: TaskClaim,
    *,
    error_code: str,
    clock: Clock | None = None,
    jitter: Jitter | None = None,
) -> TaskFailureResult:
    if not isinstance(claim, TaskClaim):
        raise TypeError("claim must be a TaskClaim")
    error_code = _validate_error_code(error_code)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        run = TaskRun.objects.select_for_update().get(run_id=claim.run_id)
        if run.status != TaskRunStatus.RUNNING or run.lease_token != claim.lease_token:
            return TaskFailureResult(StartOutcome.BUSY)
        run.heartbeat_at = now
        if run.attempt >= MAX_ATTEMPTS:
            _final_failure_locked(
                run,
                error_code=error_code,
                now=now,
                clock=active_clock,
            )
            return TaskFailureResult(StartOutcome.FINAL_FAILED)

        countdown = retry_delay_seconds(run.attempt, jitter=jitter)
        run.status = TaskRunStatus.RETRY_WAIT
        run.available_at = now + timedelta(seconds=countdown)
        run.last_error_code = error_code
        run.lease_token = None
        run.lease_expires_at = None
        run.save(
            update_fields=(
                "status",
                "available_at",
                "last_error_code",
                "heartbeat_at",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            )
        )
        return TaskFailureResult(
            StartOutcome.RETRY_SCHEDULED,
            retry_after_seconds=countdown,
        )


def recover_expired_task_leases(
    *,
    batch_size: int = 100,
    clock: Clock | None = None,
    jitter: Jitter | None = None,
) -> int:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1_000
    ):
        raise ValueError("Invalid batch_size")
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        runs = list(
            TaskRun.objects.select_for_update(skip_locked=True)
            .filter(
                status=TaskRunStatus.RUNNING,
                lease_expires_at__lte=now,
            )
            .order_by("lease_expires_at", "run_id")[:batch_size]
        )
        for run in runs:
            _release_expired_locked(
                run,
                now=now,
                clock=active_clock,
                jitter=jitter,
            )
    return len(runs)


def execute_tracked_task(
    *,
    task_name: str,
    business_object: str,
    idempotency_key: str,
    celery_id: str,
    service: TaskService | None = None,
    heartbeat_service: HeartbeatTaskService | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    clock: Clock | None = None,
    jitter: Jitter | None = None,
) -> TaskStartResult:
    if (service is None) == (heartbeat_service is None):
        raise TypeError("exactly one task service must be callable")
    if service is not None and not callable(service):
        raise TypeError("service must be callable")
    if heartbeat_service is not None and not callable(heartbeat_service):
        raise TypeError("heartbeat_service must be callable")
    active_clock = clock or SystemClock()
    start = claim_task(
        task_name=task_name,
        business_object=business_object,
        idempotency_key=idempotency_key,
        celery_id=celery_id,
        lease_seconds=lease_seconds,
        clock=active_clock,
        jitter=jitter,
    )
    if start.outcome == StartOutcome.ALREADY_SUCCEEDED:
        return start
    if start.outcome == StartOutcome.FINAL_FAILED:
        raise TaskFinalFailed(error_code=start.error_code or TASK_UNEXPECTED_ERROR)
    if start.outcome == StartOutcome.BUSY:
        raise TaskRetryScheduled(
            countdown=max(1, start.retry_after_seconds),
            error_code=TASK_BUSY,
        )
    claim = start.claim
    if claim is None:
        raise RuntimeError("Claimed task is missing its lease")

    token = bind_trace_code(claim.trace_code)
    try:
        try:
            if heartbeat_service is None:
                assert service is not None
                service_result = service(business_object)
            else:

                def renew_lease() -> None:
                    if not heartbeat_task(
                        claim,
                        lease_seconds=lease_seconds,
                        clock=active_clock,
                    ):
                        raise TaskLeaseLost("task lease is no longer owned")

                service_result = heartbeat_service(business_object, renew_lease)
            result_ref = _result_ref(service_result)
        except Exception as error:
            error_code = (
                error.error_code
                if isinstance(error, RetryableTaskError)
                else TASK_UNEXPECTED_ERROR
            )
            failed = fail_task(
                claim,
                error_code=error_code,
                clock=active_clock,
                jitter=jitter,
            )
            if failed.outcome == StartOutcome.FINAL_FAILED:
                raise TaskFinalFailed(error_code=error_code) from None
            if failed.outcome == StartOutcome.RETRY_SCHEDULED:
                raise TaskRetryScheduled(
                    countdown=failed.retry_after_seconds,
                    error_code=error_code,
                ) from None
            raise TaskLeaseLost("task lease is no longer owned") from None

        if not complete_task(claim, result_ref=result_ref, clock=active_clock):
            raise TaskLeaseLost("task lease is no longer owned")
        return TaskStartResult(
            StartOutcome.SUCCEEDED,
            result_ref=result_ref,
        )
    finally:
        reset_trace_code(token)
