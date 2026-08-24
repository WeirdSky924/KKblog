from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic as system_monotonic

from django.db import close_old_connections, connections, transaction

from apps.core.events import enqueue_event
from apps.core.time.clock import Clock, SystemClock
from apps.operations.public import TaskCancelled, current_task_run_id

from ..checks import DomainRateLimiter
from ..events import CHECK_SUMMARY
from ..models import OpportunityCheckRun, OpportunityCheckRunSource
from .runner import ClientFactory, _default_client_factory, run_source_check

logger = logging.getLogger(__name__)
SOURCE_INTERRUPTED = "opportunities.source_interrupted.v1"


def _finish_run(run_id: str, *, clock: Clock) -> OpportunityCheckRun:
    with transaction.atomic():
        run = OpportunityCheckRun.objects.select_for_update().get(pk=run_id)
        counts = {
            state: run.source_runs.filter(state=state).count()
            for state in OpportunityCheckRunSource.State.values
        }
        run.succeeded_sources = counts[OpportunityCheckRunSource.State.SUCCEEDED]
        run.failed_sources = counts[OpportunityCheckRunSource.State.FAILED]
        run.truncated_sources = counts[OpportunityCheckRunSource.State.TRUNCATED]
        run.skipped_sources = counts[OpportunityCheckRunSource.State.SKIPPED]
        run.not_executed_sources = counts[OpportunityCheckRunSource.State.NOT_EXECUTED]
        run.created_opportunities = sum(
            run.source_runs.values_list("created_opportunities", flat=True)
        )
        run.changed_opportunities = sum(
            run.source_runs.values_list("changed_opportunities", flat=True)
        )
        run.missing_opportunities = sum(
            run.source_runs.values_list("missing_opportunities", flat=True)
        )
        run.failed_opportunity_checks = sum(
            run.source_runs.values_list("failed_opportunity_checks", flat=True)
        )
        if run.state == OpportunityCheckRun.State.CANCEL_REQUESTED:
            run.state = OpportunityCheckRun.State.CANCELLED
        elif run.failed_sources and not (
            run.succeeded_sources or run.truncated_sources or run.skipped_sources
        ):
            run.state = OpportunityCheckRun.State.FAILED
        elif run.failed_sources or run.skipped_sources or run.failed_opportunity_checks:
            run.state = OpportunityCheckRun.State.PARTIAL
        elif run.truncated_sources:
            run.state = OpportunityCheckRun.State.TRUNCATED
        else:
            run.state = OpportunityCheckRun.State.SUCCEEDED
        run.current_source = None
        run.completed_at = clock.now()
        run.save(
            update_fields=(
                "state",
                "current_source",
                "succeeded_sources",
                "failed_sources",
                "truncated_sources",
                "skipped_sources",
                "not_executed_sources",
                "created_opportunities",
                "changed_opportunities",
                "missing_opportunities",
                "failed_opportunity_checks",
                "completed_at",
                "updated_at",
            )
        )
        if (
            run.failed_sources
            or run.truncated_sources
            or run.skipped_sources
            or run.created_opportunities
            or run.changed_opportunities
            or run.missing_opportunities
            or run.failed_opportunity_checks
        ):
            enqueue_event(
                CHECK_SUMMARY,
                aggregate_type="opportunity_check_run",
                aggregate_id=run.id,
                payload={
                    "state": run.state,
                    "succeeded": run.succeeded_sources,
                    "failed": run.failed_sources,
                    "truncated": run.truncated_sources,
                    "skipped": run.skipped_sources,
                    "not_executed": run.not_executed_sources,
                    "created": run.created_opportunities,
                    "changed": run.changed_opportunities,
                    "missing": run.missing_opportunities,
                    "job_failures": run.failed_opportunity_checks,
                },
            )
        return run


def _cancel_pending(run: OpportunityCheckRun, *, clock: Clock) -> None:
    run.source_runs.filter(state=OpportunityCheckRunSource.State.PENDING).update(
        state=OpportunityCheckRunSource.State.NOT_EXECUTED,
        completed_at=clock.now(),
    )


def _start_run(run_id: str, *, task_run_id: str, clock: Clock) -> OpportunityCheckRun:
    with transaction.atomic():
        run = OpportunityCheckRun.objects.select_for_update().get(pk=run_id)
        if run.state in (
            OpportunityCheckRun.State.SUCCEEDED,
            OpportunityCheckRun.State.PARTIAL,
            OpportunityCheckRun.State.FAILED,
            OpportunityCheckRun.State.TRUNCATED,
            OpportunityCheckRun.State.CANCELLED,
        ):
            return run
        if run.state == OpportunityCheckRun.State.CANCEL_REQUESTED:
            _cancel_pending(run, clock=clock)
            return _finish_run(run.id, clock=clock)
        run.state = OpportunityCheckRun.State.RUNNING
        run.started_at = run.started_at or clock.now()
        if task_run_id:
            run.task_run_id = task_run_id
        run.save(update_fields=("state", "started_at", "task_run_id", "updated_at"))
        return run


def _start_source_item(item_id: int, *, clock: Clock):
    with transaction.atomic():
        item = OpportunityCheckRunSource.objects.select_for_update().get(pk=item_id)
        run = OpportunityCheckRun.objects.select_for_update().get(pk=item.run_id)
        if run.state == OpportunityCheckRun.State.CANCEL_REQUESTED:
            _cancel_pending(run, clock=clock)
            return None, _finish_run(run.id, clock=clock)
        item.state = OpportunityCheckRunSource.State.RUNNING
        item.started_at = clock.now()
        item.save(update_fields=("state", "started_at"))
        run.current_source_id = item.source_id
        run.save(update_fields=("current_source", "updated_at"))
        return item, run


def _release_source_item(item_id: int) -> None:
    with transaction.atomic():
        item = OpportunityCheckRunSource.objects.select_for_update().get(pk=item_id)
        item.state = OpportunityCheckRunSource.State.PENDING
        item.started_at = None
        item.safe_error_code = SOURCE_INTERRUPTED
        item.save(update_fields=("state", "started_at", "safe_error_code"))
        OpportunityCheckRun.objects.filter(pk=item.run_id).update(current_source=None)


def _release_source_item_safely(item_id: int) -> None:
    close_old_connections()
    try:
        _release_source_item(item_id)
        return
    except Exception:
        connections.close_all()
    try:
        _release_source_item(item_id)
    except Exception:
        connections.close_all()
        logger.error(
            "Opportunity source item recovery failed item_id=%s",
            item_id,
        )


def _complete_source_item(item_id: int, result, *, clock: Clock) -> None:
    with transaction.atomic():
        item = OpportunityCheckRunSource.objects.select_for_update().get(pk=item_id)
        item.state = result.state
        item.source_check_id = result.source_check_id
        item.opportunity_checks = result.opportunity_checks
        item.created_opportunities = result.created
        item.changed_opportunities = result.changed
        item.missing_opportunities = result.missing
        item.failed_opportunity_checks = result.failed_opportunity_checks
        item.safe_error_code = result.safe_error_code
        item.completed_at = clock.now()
        item.save(
            update_fields=(
                "state",
                "source_check",
                "opportunity_checks",
                "created_opportunities",
                "changed_opportunities",
                "missing_opportunities",
                "failed_opportunity_checks",
                "safe_error_code",
                "completed_at",
            )
        )


def execute_check_run(
    run_id: str,
    heartbeat: Callable[[], None],
    *,
    client_factory: ClientFactory = _default_client_factory,
    rate_limiter: DomainRateLimiter | None = None,
    clock: Clock | None = None,
    monotonic: Callable[[], float] = system_monotonic,
) -> str:
    if not callable(heartbeat):
        raise TypeError("heartbeat must be callable")
    active_clock = clock or SystemClock()
    task_run_id = current_task_run_id() or ""
    run = _start_run(run_id, task_run_id=task_run_id, clock=active_clock)
    if run.state == OpportunityCheckRun.State.CANCELLED:
        raise TaskCancelled(result_ref=f"opportunity-run:{run.id}:cancelled")
    if run.state not in (
        OpportunityCheckRun.State.PENDING,
        OpportunityCheckRun.State.RUNNING,
    ):
        return f"opportunity-run:{run.id}:{run.state.lower()}"

    limiter = rate_limiter or DomainRateLimiter()
    item_ids = (
        OpportunityCheckRunSource.objects.filter(
            run_id=run_id,
            state=OpportunityCheckRunSource.State.PENDING,
        )
        .order_by("position")
        .values_list("id", flat=True)
    )
    for item_id in item_ids.iterator(chunk_size=50):
        heartbeat()
        item, current_run = _start_source_item(item_id, clock=active_clock)
        if item is None:
            raise TaskCancelled(
                result_ref=f"opportunity-run:{current_run.id}:cancelled"
            )
        try:
            result = run_source_check(
                source_id=item.source_id,
                trigger=current_run.trigger,
                task_run_id=task_run_id,
                heartbeat=heartbeat,
                rate_limiter=limiter,
                client_factory=client_factory,
                clock=active_clock,
                monotonic=monotonic,
            )
        except Exception:
            _release_source_item_safely(item_id)
            raise
        _complete_source_item(item_id, result, clock=active_clock)
    completed = _finish_run(run_id, clock=active_clock)
    if completed.state == OpportunityCheckRun.State.CANCELLED:
        raise TaskCancelled(result_ref=f"opportunity-run:{completed.id}:cancelled")
    return f"opportunity-run:{completed.id}:{completed.state.lower()}"


__all__ = ["execute_check_run"]
