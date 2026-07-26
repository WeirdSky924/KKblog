from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction

from apps.core.events.outbox import enqueue_event
from apps.core.time.clock import Clock, FrozenClock, SystemClock
from apps.operations.events import CAPACITY_THRESHOLD_CHANGED, SERVICE_HEALTH_CHANGED
from apps.operations.models import (
    CapacitySnapshot,
    OperationalAlertKind,
    OperationalAlertSeverity,
    ServiceHealthSnapshot,
    ServiceHealthStatus,
)

from .alerts import (
    CAPACITY_LOW_ERROR,
    SERVICE_UNAVAILABLE_ERROR,
    record_operational_state_alert,
    resolve_operational_state_alert,
)
from .capacity import CapacityPolicy, CapacitySample, CapacityState

_SOURCE_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_TRACE_CODE = re.compile(r"trc_[0-9a-hjkmnp-tv-z]{26}\Z")


class MonitoringConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CapacityMonitoringResult:
    source_key: str
    previous_state: CapacityState | None
    current_state: CapacityState
    changed: bool
    duplicate: bool
    sample_count: int


@dataclass(frozen=True, slots=True)
class ServiceHealthMonitoringResult:
    source_key: str
    previous_status: ServiceHealthStatus | None
    current_status: ServiceHealthStatus
    changed: bool
    duplicate: bool
    check_count: int


def _source_key(value: str) -> str:
    if not isinstance(value, str) or not _SOURCE_KEY.fullmatch(value):
        raise ValueError("Invalid monitoring source_key")
    return value


def _trace_code(value: str) -> str:
    if not isinstance(value, str) or not _TRACE_CODE.fullmatch(value):
        raise ValueError("Invalid monitoring trace_code")
    return value


def _capacity_result(
    snapshot: CapacitySnapshot,
    *,
    previous_state: CapacityState | None,
    changed: bool,
    duplicate: bool,
) -> CapacityMonitoringResult:
    return CapacityMonitoringResult(
        source_key=snapshot.source_key,
        previous_state=previous_state,
        current_state=CapacityState(snapshot.state),
        changed=changed,
        duplicate=duplicate,
        sample_count=snapshot.sample_count,
    )


def record_capacity_sample(
    sample: CapacitySample,
    *,
    source_key: str,
    trace_code: str,
    policy: CapacityPolicy | None = None,
) -> CapacityMonitoringResult:
    if not isinstance(sample, CapacitySample):
        raise TypeError("sample must be a CapacitySample")
    source = _source_key(source_key)
    trace = _trace_code(trace_code)
    decision = (policy or CapacityPolicy()).evaluate(sample)
    current_state = decision.state
    with transaction.atomic():
        snapshot = (
            CapacitySnapshot.objects.select_for_update().filter(pk=source).first()
        )
        previous_state = CapacityState(snapshot.state) if snapshot is not None else None
        if snapshot is not None and sample.observed_at < snapshot.observed_at:
            raise MonitoringConflict("Capacity sample is older than current state")
        if snapshot is not None and sample.observed_at == snapshot.observed_at:
            if (
                snapshot.total_bytes != sample.total_bytes
                or snapshot.free_bytes != sample.free_bytes
                or previous_state != current_state
            ):
                raise MonitoringConflict(
                    "Capacity sample timestamp has conflicting facts"
                )
            return _capacity_result(
                snapshot,
                previous_state=previous_state,
                changed=False,
                duplicate=True,
            )

        changed = previous_state != current_state and (
            previous_state is not None or current_state != CapacityState.NORMAL
        )
        if snapshot is None:
            snapshot = CapacitySnapshot.objects.create(
                source_key=source,
                state=current_state,
                total_bytes=sample.total_bytes,
                free_bytes=sample.free_bytes,
                observed_at=sample.observed_at,
                state_changed_at=sample.observed_at,
            )
        else:
            snapshot.state = current_state
            snapshot.total_bytes = sample.total_bytes
            snapshot.free_bytes = sample.free_bytes
            snapshot.observed_at = sample.observed_at
            snapshot.sample_count += 1
            update_fields = [
                "state",
                "total_bytes",
                "free_bytes",
                "observed_at",
                "sample_count",
                "updated_at",
            ]
            if previous_state != current_state:
                snapshot.state_changed_at = sample.observed_at
                update_fields.append("state_changed_at")
            snapshot.save(update_fields=tuple(update_fields))

        if current_state == CapacityState.NORMAL:
            resolve_operational_state_alert(
                kind=OperationalAlertKind.CAPACITY,
                source_key=source,
                state_code=current_state,
                trace_code=trace,
                occurred_at=sample.observed_at,
            )
        else:
            severity = (
                OperationalAlertSeverity.WARNING
                if current_state == CapacityState.WARN
                else OperationalAlertSeverity.CRITICAL
            )
            record_operational_state_alert(
                kind=OperationalAlertKind.CAPACITY,
                source_key=source,
                state_code=current_state,
                error_code=CAPACITY_LOW_ERROR,
                severity=severity,
                trace_code=trace,
                occurred_at=sample.observed_at,
            )

        if changed:
            enqueue_event(
                CAPACITY_THRESHOLD_CHANGED,
                aggregate_type="capacity_state",
                aggregate_id=source,
                payload={
                    "source_key": source,
                    "previous_state": previous_state or "unknown",
                    "current_state": current_state,
                },
                trace_code=trace,
                clock=FrozenClock(sample.observed_at),
            )
        return _capacity_result(
            snapshot,
            previous_state=previous_state,
            changed=changed,
            duplicate=False,
        )


def _health_result(
    snapshot: ServiceHealthSnapshot,
    *,
    previous_status: ServiceHealthStatus | None,
    changed: bool,
    duplicate: bool,
) -> ServiceHealthMonitoringResult:
    return ServiceHealthMonitoringResult(
        source_key=snapshot.source_key,
        previous_status=previous_status,
        current_status=ServiceHealthStatus(snapshot.status),
        changed=changed,
        duplicate=duplicate,
        check_count=snapshot.check_count,
    )


def sample_service_health(
    *,
    source_key: str,
    checker: Callable[[], bool],
    trace_code: str,
    clock: Clock | None = None,
) -> ServiceHealthMonitoringResult:
    source = _source_key(source_key)
    trace = _trace_code(trace_code)
    if not callable(checker):
        raise TypeError("Service health checker must be callable")
    available = checker()
    if type(available) is not bool:
        raise TypeError("Service health checker must return a boolean")
    observed_at = (clock or SystemClock()).now()
    current_status = (
        ServiceHealthStatus.HEALTHY if available else ServiceHealthStatus.UNAVAILABLE
    )
    with transaction.atomic():
        snapshot = (
            ServiceHealthSnapshot.objects.select_for_update().filter(pk=source).first()
        )
        previous_status = (
            ServiceHealthStatus(snapshot.status) if snapshot is not None else None
        )
        if snapshot is not None and observed_at < snapshot.last_checked_at:
            raise MonitoringConflict("Health sample is older than current state")
        if snapshot is not None and observed_at == snapshot.last_checked_at:
            if previous_status != current_status:
                raise MonitoringConflict("Health timestamp has conflicting facts")
            return _health_result(
                snapshot,
                previous_status=previous_status,
                changed=False,
                duplicate=True,
            )

        changed = previous_status != current_status and (
            previous_status is not None or current_status != ServiceHealthStatus.HEALTHY
        )
        if snapshot is None:
            snapshot = ServiceHealthSnapshot.objects.create(
                source_key=source,
                status=current_status,
                first_checked_at=observed_at,
                last_checked_at=observed_at,
                status_changed_at=observed_at,
                last_success_at=(
                    observed_at
                    if current_status == ServiceHealthStatus.HEALTHY
                    else None
                ),
                consecutive_failures=(
                    1 if current_status == ServiceHealthStatus.UNAVAILABLE else 0
                ),
                last_error_code=(
                    SERVICE_UNAVAILABLE_ERROR
                    if current_status == ServiceHealthStatus.UNAVAILABLE
                    else ""
                ),
            )
        else:
            snapshot.status = current_status
            snapshot.check_count += 1
            snapshot.last_checked_at = observed_at
            if current_status == ServiceHealthStatus.HEALTHY:
                snapshot.consecutive_failures = 0
                snapshot.last_success_at = observed_at
                snapshot.last_error_code = ""
            else:
                snapshot.consecutive_failures = (
                    snapshot.consecutive_failures + 1
                    if previous_status == ServiceHealthStatus.UNAVAILABLE
                    else 1
                )
                snapshot.last_error_code = SERVICE_UNAVAILABLE_ERROR
            update_fields = [
                "status",
                "check_count",
                "last_checked_at",
                "consecutive_failures",
                "last_success_at",
                "last_error_code",
                "updated_at",
            ]
            if previous_status != current_status:
                snapshot.status_changed_at = observed_at
                update_fields.append("status_changed_at")
            snapshot.save(update_fields=tuple(update_fields))

        if current_status == ServiceHealthStatus.HEALTHY:
            resolve_operational_state_alert(
                kind=OperationalAlertKind.SERVICE_HEALTH,
                source_key=source,
                state_code=current_status,
                trace_code=trace,
                occurred_at=observed_at,
            )
        else:
            record_operational_state_alert(
                kind=OperationalAlertKind.SERVICE_HEALTH,
                source_key=source,
                state_code=current_status,
                error_code=SERVICE_UNAVAILABLE_ERROR,
                severity=OperationalAlertSeverity.CRITICAL,
                trace_code=trace,
                occurred_at=observed_at,
            )

        if changed:
            enqueue_event(
                SERVICE_HEALTH_CHANGED,
                aggregate_type="service_health",
                aggregate_id=source,
                payload={
                    "source_key": source,
                    "previous_state": previous_status or "unknown",
                    "current_state": current_status,
                },
                trace_code=trace,
                clock=FrozenClock(observed_at),
            )
        return _health_result(
            snapshot,
            previous_status=previous_status,
            changed=changed,
            duplicate=False,
        )
