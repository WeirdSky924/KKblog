from dataclasses import dataclass
from datetime import datetime

from apps.operations.models import (
    CapacitySnapshot,
    OperationalAlert,
    ServiceHealthSnapshot,
)


@dataclass(frozen=True, slots=True)
class CapacityStatusItem:
    source_key: str
    state: str
    total_bytes: int
    free_bytes: int
    observed_at: datetime
    state_changed_at: datetime
    sample_count: int


@dataclass(frozen=True, slots=True)
class ServiceHealthStatusItem:
    source_key: str
    status: str
    consecutive_failures: int
    last_checked_at: datetime
    status_changed_at: datetime
    last_success_at: datetime | None
    last_error_code: str
    check_count: int


@dataclass(frozen=True, slots=True)
class ActiveAlertItem:
    alert_id: str
    kind: str
    source_key: str
    state_code: str
    severity: str
    error_code: str
    trace_code: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class MonitoringStatus:
    capacity: tuple[CapacityStatusItem, ...]
    services: tuple[ServiceHealthStatusItem, ...]
    active_alerts: tuple[ActiveAlertItem, ...]


def current_monitoring_status() -> MonitoringStatus:
    return MonitoringStatus(
        capacity=tuple(
            CapacityStatusItem(
                source_key=item.source_key,
                state=item.state,
                total_bytes=item.total_bytes,
                free_bytes=item.free_bytes,
                observed_at=item.observed_at,
                state_changed_at=item.state_changed_at,
                sample_count=item.sample_count,
            )
            for item in CapacitySnapshot.objects.order_by("source_key")
        ),
        services=tuple(
            ServiceHealthStatusItem(
                source_key=item.source_key,
                status=item.status,
                consecutive_failures=item.consecutive_failures,
                last_checked_at=item.last_checked_at,
                status_changed_at=item.status_changed_at,
                last_success_at=item.last_success_at,
                last_error_code=item.last_error_code,
                check_count=item.check_count,
            )
            for item in ServiceHealthSnapshot.objects.order_by("source_key")
        ),
        active_alerts=tuple(
            ActiveAlertItem(
                alert_id=item.id,
                kind=item.kind,
                source_key=item.source_key,
                state_code=item.state_code,
                severity=item.severity,
                error_code=item.error_code,
                trace_code=item.trace_code,
                occurrence_count=item.occurrence_count,
                first_seen_at=item.first_seen_at,
                last_seen_at=item.last_seen_at,
            )
            for item in OperationalAlert.objects.filter(active=True).order_by(
                "-last_seen_at", "-id"
            )
        ),
    )
