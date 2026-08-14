from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.core.time.clock import Clock, SystemClock
from apps.operations.public import record_audit_entry

from ..models import (
    OpportunityCheck,
    OpportunityCheckRun,
    OpportunityCheckRunSource,
    OpportunitySource,
)
from .common import OpportunityCommandError, require_administrator, uuid_value
from .sources import SourceResult, activate_source

RunDispatcher = Callable[[str], None]
_ACTIVE_STATES = (
    OpportunityCheckRun.State.PENDING,
    OpportunityCheckRun.State.RUNNING,
    OpportunityCheckRun.State.CANCEL_REQUESTED,
)


@dataclass(frozen=True, slots=True)
class CheckRunRequestResult:
    run_id: str
    state: str
    reused: bool


@dataclass(frozen=True, slots=True)
class CheckRunCancellationResult:
    run_id: str
    state: str


@dataclass(frozen=True, slots=True)
class SourceActivationCheckResult:
    source: SourceResult
    check_run: CheckRunRequestResult


def _active_run(*, lock: bool = False) -> OpportunityCheckRun | None:
    rows = OpportunityCheckRun.objects
    if lock:
        rows = rows.select_for_update()
    return rows.filter(state__in=_ACTIVE_STATES).first()


def _source(identity) -> OpportunitySource:
    try:
        return OpportunitySource.objects.get(pk=identity, enabled=True)
    except OpportunitySource.DoesNotExist:
        raise OpportunityCommandError(
            "opportunities.source_not_found.v1", "招聘来源不存在或未启用。"
        ) from None


def _manual_audit(
    *,
    actor_id,
    run: OpportunityCheckRun,
    trace_code: str,
    client_ip: str,
    action: str,
    reused: bool,
    source_id=None,
) -> None:
    after = {
        "run_id": run.id,
        "kind": run.kind,
        "state": run.state,
        "reused": reused,
    }
    if source_id is not None:
        after["source_id"] = str(source_id)
    record_audit_entry(
        action=action,
        actor_id=actor_id,
        target_id=run.id,
        trace_code=trace_code,
        client_ip=client_ip,
        before={},
        after=after,
        summary="Request opportunity check run",
    )


def _reuse_source_run(
    active: OpportunityCheckRun, source: OpportunitySource
) -> OpportunityCheckRun | None:
    if active.kind == OpportunityCheckRun.Kind.SOURCE:
        return active if active.source_runs.filter(source=source).exists() else None
    if active.kind == OpportunityCheckRun.Kind.FULL:
        if active.current_source_id == source.id:
            return active
        raise OpportunityCommandError(
            "opportunities.full_check_running.v1",
            "全部来源检查正在运行，请等待完成后重试。",
        )
    return None


def request_source_check(
    *,
    actor_id,
    source_id,
    trace_code: str,
    client_ip: str,
    dispatcher: RunDispatcher,
    clock: Clock | None = None,
) -> CheckRunRequestResult:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        source_id,
        code="opportunities.source_not_found.v1",
        message="招聘来源不存在。",
    )
    if not callable(dispatcher):
        raise TypeError("dispatcher must be callable")
    del clock
    with transaction.atomic():
        source = _source(identity)
        active = _active_run(lock=True)
        if active is not None:
            reused_run = _reuse_source_run(active, source)
            if reused_run is None:
                raise OpportunityCommandError(
                    "opportunities.check_busy.v1", "另一个来源检查正在运行。"
                )
            _manual_audit(
                actor_id=actor,
                run=reused_run,
                trace_code=trace_code,
                client_ip=client_ip,
                action="opportunities.check.request_source",
                reused=True,
                source_id=source.id,
            )
            return CheckRunRequestResult(reused_run.id, reused_run.state, True)
        try:
            with transaction.atomic():
                run = OpportunityCheckRun.objects.create(
                    kind=OpportunityCheckRun.Kind.SOURCE,
                    trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
                    requested_by_id=actor,
                    total_sources=1,
                )
                OpportunityCheckRunSource.objects.create(
                    run=run,
                    source=source,
                    position=1,
                )
        except IntegrityError:
            active = _active_run(lock=True)
            if active is None:
                raise
            reused_run = _reuse_source_run(active, source)
            if reused_run is None:
                raise OpportunityCommandError(
                    "opportunities.check_busy.v1", "另一个来源检查正在运行。"
                ) from None
            run = reused_run
            reused = True
        else:
            reused = False
        _manual_audit(
            actor_id=actor,
            run=run,
            trace_code=trace_code,
            client_ip=client_ip,
            action="opportunities.check.request_source",
            reused=reused,
            source_id=source.id,
        )
        if not reused:
            transaction.on_commit(lambda: dispatcher(run.id))
    return CheckRunRequestResult(run.id, run.state, reused)


def activate_source_and_request_check(
    *,
    actor_id,
    source_id,
    trace_code: str,
    client_ip: str,
    dispatcher: RunDispatcher,
    clock: Clock | None = None,
) -> SourceActivationCheckResult:
    if not callable(dispatcher):
        raise TypeError("dispatcher must be callable")
    with transaction.atomic():
        source = activate_source(
            actor_id=actor_id,
            source_id=source_id,
            trace_code=trace_code,
            client_ip=client_ip,
        )
        check_run = request_source_check(
            actor_id=actor_id,
            source_id=source.source_id,
            trace_code=trace_code,
            client_ip=client_ip,
            dispatcher=dispatcher,
            clock=clock,
        )
    return SourceActivationCheckResult(source=source, check_run=check_run)


def _create_full_run(
    *,
    trigger: str,
    actor_id=None,
) -> OpportunityCheckRun:
    sources = list(
        OpportunitySource.objects.filter(enabled=True).order_by(
            "normalized_company_name", "source_type", "id"
        )
    )
    run = OpportunityCheckRun.objects.create(
        kind=OpportunityCheckRun.Kind.FULL,
        trigger=trigger,
        requested_by_id=actor_id,
        total_sources=len(sources),
    )
    OpportunityCheckRunSource.objects.bulk_create(
        [
            OpportunityCheckRunSource(run=run, source=source, position=position)
            for position, source in enumerate(sources, start=1)
        ]
    )
    return run


def request_full_check(
    *,
    actor_id,
    trace_code: str,
    client_ip: str,
    dispatcher: RunDispatcher,
    clock: Clock | None = None,
) -> CheckRunRequestResult:
    del clock
    actor = require_administrator(actor_id)
    if not callable(dispatcher):
        raise TypeError("dispatcher must be callable")
    with transaction.atomic():
        active = _active_run(lock=True)
        if active is not None:
            if active.kind != OpportunityCheckRun.Kind.FULL:
                raise OpportunityCommandError(
                    "opportunities.check_busy.v1", "单个来源检查正在运行。"
                )
            run = active
            reused = True
        else:
            try:
                with transaction.atomic():
                    run = _create_full_run(
                        trigger=OpportunityCheck.Trigger.MANUAL_ALL,
                        actor_id=actor,
                    )
            except IntegrityError:
                run = _active_run(lock=True)
                if run is None or run.kind != OpportunityCheckRun.Kind.FULL:
                    raise OpportunityCommandError(
                        "opportunities.check_busy.v1", "单个来源检查正在运行。"
                    ) from None
                reused = True
            else:
                reused = False
        _manual_audit(
            actor_id=actor,
            run=run,
            trace_code=trace_code,
            client_ip=client_ip,
            action="opportunities.check.request_full",
            reused=reused,
        )
        if not reused:
            transaction.on_commit(lambda: dispatcher(run.id))
    return CheckRunRequestResult(run.id, run.state, reused)


def request_scheduled_full_check(*, dispatcher: RunDispatcher) -> CheckRunRequestResult:
    if not callable(dispatcher):
        raise TypeError("dispatcher must be callable")
    with transaction.atomic():
        active = _active_run(lock=True)
        if active is not None:
            return CheckRunRequestResult(active.id, active.state, True)
        try:
            with transaction.atomic():
                run = _create_full_run(trigger=OpportunityCheck.Trigger.SCHEDULED)
        except IntegrityError:
            run = _active_run(lock=True)
            if run is None:
                raise
            return CheckRunRequestResult(run.id, run.state, True)
        transaction.on_commit(lambda: dispatcher(run.id))
    return CheckRunRequestResult(run.id, run.state, False)


def dispatch_pending_check_runs(
    *,
    dispatcher: RunDispatcher,
    batch_size: int = 10,
) -> int:
    if not callable(dispatcher):
        raise TypeError("dispatcher must be callable")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("batch_size must be an integer")
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    run_ids = list(
        OpportunityCheckRun.objects.filter(state=OpportunityCheckRun.State.PENDING)
        .order_by("created_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    for run_id in run_ids:
        dispatcher(run_id)
    return len(run_ids)


def request_check_cancellation(
    *,
    actor_id,
    run_id: str,
    trace_code: str,
    client_ip: str,
    clock: Clock | None = None,
) -> CheckRunCancellationResult:
    actor = require_administrator(actor_id)
    now = (clock or SystemClock()).now()
    with transaction.atomic():
        try:
            run = OpportunityCheckRun.objects.select_for_update().get(pk=run_id)
        except OpportunityCheckRun.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.check_run_not_found.v1", "检查任务不存在。"
            ) from None
        before = {"run_id": run.id, "kind": run.kind, "state": run.state}
        if run.state == OpportunityCheckRun.State.PENDING:
            run.source_runs.filter(
                state=OpportunityCheckRunSource.State.PENDING
            ).update(
                state=OpportunityCheckRunSource.State.NOT_EXECUTED,
                completed_at=now,
            )
            run.state = OpportunityCheckRun.State.CANCELLED
            run.cancel_requested_at = now
            run.completed_at = now
            run.current_source = None
            run.not_executed_sources = run.source_runs.filter(
                state=OpportunityCheckRunSource.State.NOT_EXECUTED
            ).count()
            run.save(
                update_fields=(
                    "state",
                    "cancel_requested_at",
                    "completed_at",
                    "current_source",
                    "not_executed_sources",
                    "updated_at",
                )
            )
        elif run.state == OpportunityCheckRun.State.RUNNING:
            run.state = OpportunityCheckRun.State.CANCEL_REQUESTED
            run.cancel_requested_at = now
            run.save(update_fields=("state", "cancel_requested_at", "updated_at"))
        record_audit_entry(
            action="opportunities.check.cancel",
            actor_id=actor,
            target_id=run.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after={"run_id": run.id, "kind": run.kind, "state": run.state},
            summary="Request opportunity check cancellation",
        )
    return CheckRunCancellationResult(run.id, run.state)


__all__ = [
    "CheckRunCancellationResult",
    "CheckRunRequestResult",
    "SourceActivationCheckResult",
    "activate_source_and_request_check",
    "dispatch_pending_check_runs",
    "request_check_cancellation",
    "request_full_check",
    "request_scheduled_full_check",
    "request_source_check",
]
