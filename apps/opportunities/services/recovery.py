from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.db import close_old_connections, transaction

from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, FrozenClock, SystemClock
from apps.operations.public import (
    due_task_run_business_objects,
    recover_expired_task_leases,
)

from ..events import CHECK_STALLED
from ..models import OpportunityCheckRun, OpportunityCheckRunSource
from .run_execution import _finish_run

RUN_CHECK_TASK_NAME = "apps.opportunities.run_check"
RUN_BUSINESS_PREFIX = "opportunity-run:"
LEASE_EXPIRED_ERROR = "opportunities.check_lease_expired.v1"
SOURCE_TIMEOUT_WARNING = "opportunities.source_timeout_warning.v1"


@dataclass(frozen=True, slots=True)
class CheckLeaseRecoveryResult:
    recovered: int
    redispatched: int
    stalled: int = 0


def _run_id(value: str) -> str | None:
    if not isinstance(value, str) or not value.startswith(RUN_BUSINESS_PREFIX):
        return None
    try:
        return normalize_ulid(value.removeprefix(RUN_BUSINESS_PREFIX))
    except (TypeError, ValueError):
        return None


def _stalled_payload(*, run, item, reason: str, attempt: int, final_failed: bool):
    return {
        "run_id": run.id,
        "source_name": item.source.company_name,
        "source_position": item.position,
        "reason": reason,
        "attempt": attempt,
        "final_failed": final_failed,
        "max_duration_seconds": (
            item.source.max_duration_seconds if reason == "SOURCE_TIMEOUT" else 0
        ),
    }


def _enqueue_stalled_event(
    *,
    run,
    item,
    reason: str,
    attempt: int,
    final_failed: bool,
    now,
    trace_code: str | None = None,
) -> None:
    enqueue_event(
        CHECK_STALLED,
        aggregate_type="opportunity_check_run",
        aggregate_id=run.id,
        payload=_stalled_payload(
            run=run,
            item=item,
            reason=reason,
            attempt=attempt,
            final_failed=final_failed,
        ),
        trace_code=trace_code,
        clock=FrozenClock(now),
    )


def _reconcile_recovered_task(task_run, final_failed: bool, *, now) -> None:
    if task_run.task_name != RUN_CHECK_TASK_NAME:
        return
    run_id = _run_id(task_run.business_object)
    if run_id is None:
        return
    with transaction.atomic():
        run = OpportunityCheckRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.state not in {
            OpportunityCheckRun.State.RUNNING,
            OpportunityCheckRun.State.CANCEL_REQUESTED,
        }:
            return
        running_items = list(
            OpportunityCheckRunSource.objects.select_for_update()
            .select_related("source")
            .filter(
                run=run,
                state=OpportunityCheckRunSource.State.RUNNING,
            )
            .order_by("position", "id")
        )
        if final_failed:
            for item in running_items:
                item.state = OpportunityCheckRunSource.State.FAILED
                item.safe_error_code = LEASE_EXPIRED_ERROR
                item.completed_at = now
                item.save(update_fields=("state", "safe_error_code", "completed_at"))
                _enqueue_stalled_event(
                    run=run,
                    item=item,
                    reason="LEASE_EXPIRED",
                    attempt=task_run.attempt,
                    final_failed=True,
                    now=now,
                    trace_code=task_run.trace_code,
                )
            if not running_items:
                pending_item = (
                    OpportunityCheckRunSource.objects.select_for_update()
                    .select_related("source")
                    .filter(run=run, state=OpportunityCheckRunSource.State.PENDING)
                    .order_by("position", "id")
                    .first()
                )
                if pending_item is not None:
                    pending_item.state = OpportunityCheckRunSource.State.FAILED
                    pending_item.safe_error_code = LEASE_EXPIRED_ERROR
                    pending_item.completed_at = now
                    pending_item.save(
                        update_fields=("state", "safe_error_code", "completed_at")
                    )
                    _enqueue_stalled_event(
                        run=run,
                        item=pending_item,
                        reason="LEASE_EXPIRED",
                        attempt=task_run.attempt,
                        final_failed=True,
                        now=now,
                        trace_code=task_run.trace_code,
                    )
            run.source_runs.filter(
                state=OpportunityCheckRunSource.State.PENDING
            ).update(
                state=OpportunityCheckRunSource.State.NOT_EXECUTED,
                safe_error_code=LEASE_EXPIRED_ERROR,
                completed_at=now,
            )
        else:
            for item in running_items:
                item.state = OpportunityCheckRunSource.State.PENDING
                item.started_at = None
                item.safe_error_code = LEASE_EXPIRED_ERROR
                item.save(update_fields=("state", "started_at", "safe_error_code"))
                _enqueue_stalled_event(
                    run=run,
                    item=item,
                    reason="LEASE_EXPIRED",
                    attempt=task_run.attempt,
                    final_failed=False,
                    now=now,
                    trace_code=task_run.trace_code,
                )
        run.current_source = None
        run.save(update_fields=("current_source", "updated_at"))
        if final_failed:
            _finish_run(run_id, clock=FrozenClock(now))


def _monitor_source_timeouts(*, now, batch_size: int) -> int:
    """Persist one warning per still-running source that exceeds its limit."""
    with transaction.atomic():
        items = list(
            OpportunityCheckRunSource.objects.select_for_update(skip_locked=True)
            .select_related("run", "source")
            .filter(
                run__state__in=(
                    OpportunityCheckRun.State.RUNNING,
                    OpportunityCheckRun.State.CANCEL_REQUESTED,
                ),
                state=OpportunityCheckRunSource.State.RUNNING,
                started_at__isnull=False,
            )
            .order_by("started_at", "id")[:batch_size]
        )
        warned = 0
        for item in items:
            if (
                item.started_at + timedelta(seconds=item.source.max_duration_seconds)
                > now
            ):
                continue
            if item.safe_error_code == SOURCE_TIMEOUT_WARNING:
                continue
            item.safe_error_code = SOURCE_TIMEOUT_WARNING
            item.save(update_fields=("safe_error_code",))
            _enqueue_stalled_event(
                run=item.run,
                item=item,
                reason="SOURCE_TIMEOUT",
                attempt=0,
                final_failed=False,
                now=now,
            )
            warned += 1
        return warned


def recover_expired_check_runs(
    *,
    dispatcher: Callable[[str], None],
    batch_size: int = 100,
    clock: Clock | None = None,
) -> CheckLeaseRecoveryResult:
    if not callable(dispatcher):
        raise TypeError("dispatcher must be callable")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1_000
    ):
        raise ValueError("Invalid batch_size")
    active_clock = clock or SystemClock()
    now = active_clock.now()
    close_old_connections()
    recovered = recover_expired_task_leases(
        batch_size=batch_size,
        clock=active_clock,
        jitter=lambda _base: 0,
        task_names=(RUN_CHECK_TASK_NAME,),
        on_recovered=lambda task_run, final_failed: _reconcile_recovered_task(
            task_run, final_failed, now=now
        ),
    )
    stalled = _monitor_source_timeouts(now=now, batch_size=batch_size)
    business_objects = due_task_run_business_objects(
        task_name=RUN_CHECK_TASK_NAME,
        now=now,
        batch_size=batch_size,
    )
    dispatched = 0
    for business_object in business_objects:
        run_id = _run_id(business_object)
        if run_id is None:
            continue
        dispatcher(run_id)
        dispatched += 1
    return CheckLeaseRecoveryResult(
        recovered=recovered,
        redispatched=dispatched,
        stalled=stalled,
    )


__all__ = [
    "CheckLeaseRecoveryResult",
    "LEASE_EXPIRED_ERROR",
    "RUN_CHECK_TASK_NAME",
    "SOURCE_TIMEOUT_WARNING",
    "recover_expired_check_runs",
]
