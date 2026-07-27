from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from celery import shared_task
from django.conf import settings

from apps.core.ids import normalize_ulid
from apps.core.observability.context import current_trace_code
from apps.core.time.clock import Clock, SystemClock
from apps.operations.services.backup import BackupRetryable, shanghai_backup_week
from apps.operations.services.capacity import filesystem_capacity_sample
from apps.operations.services.celery import execute_celery_entry
from apps.operations.services.health import application_is_ready
from apps.operations.services.monitoring import (
    record_capacity_sample,
    sample_service_health,
)
from apps.operations.services.tasks import RetryableTaskError, StartOutcome

_CAPACITY_SOURCE = "media_disk"
_HEALTH_SOURCE = "application"
WEEKLY_BACKUP_TASK_NAME = "apps.operations.weekly_backup"
EXPIRE_BACKUP_TASK_NAME = "apps.operations.expire_backups"
BACKUP_EXPIRY_DISPATCH_TASK_NAME = "apps.operations.dispatch_expired_backups"


def _window_id(moment: datetime, *, seconds: int) -> str:
    epoch_seconds = int(moment.timestamp())
    return str(epoch_seconds - epoch_seconds % seconds)


def _required_trace_code() -> str:
    trace_code = current_trace_code()
    if not trace_code:
        raise RetryableTaskError("operations.monitor_trace_missing.v1")
    return trace_code


def _capacity_service(clock: Clock) -> Callable[[str], str]:
    def run(source_key: str) -> str:
        if source_key != _CAPACITY_SOURCE:
            raise RetryableTaskError("operations.capacity_source_invalid.v1")
        sample = filesystem_capacity_sample(settings.MEDIA_ROOT, clock=clock)
        result = record_capacity_sample(
            sample,
            source_key=source_key,
            trace_code=_required_trace_code(),
        )
        return f"capacity:{source_key}:{result.current_state}:{result.sample_count}"

    return run


def _health_service(clock: Clock) -> Callable[[str], str]:
    def run(source_key: str) -> str:
        if source_key != _HEALTH_SOURCE:
            raise RetryableTaskError("operations.health_source_invalid.v1")
        result = sample_service_health(
            source_key=source_key,
            checker=application_is_ready,
            trace_code=_required_trace_code(),
            clock=clock,
        )
        return f"health:{source_key}:{result.current_status}:{result.check_count}"

    return run


def _week_from_business_object(value: str) -> str:
    prefix, separator, week_id = value.partition(":")
    if prefix != "backup" or separator != ":":
        raise ValueError("Invalid backup business object")
    return week_id


def _backup_id_from_business_object(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "backup" or parts[2] != "expire":
        raise ValueError("Invalid backup expiry business object")
    return normalize_ulid(parts[1])


def _weekly_backup_service(business_object: str, heartbeat) -> str:
    from config.backup_integrations import build_configured_weekly_backup

    week_id = _week_from_business_object(business_object)
    try:
        result = build_configured_weekly_backup(week_id, heartbeat=heartbeat)
    except BackupRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"backup:{result.backup_id}:{result.state.lower()}"


def _expire_backup_service(business_object: str) -> str:
    from config.backup_integrations import expire_configured_backup

    backup_id = _backup_id_from_business_object(business_object)
    try:
        result = expire_configured_backup(backup_id)
    except BackupRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"backup:{backup_id}:{result.state.lower()}"


def _request_id(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid backup dispatcher request ID") from None


def _dispatch_expired_backup_service(business_object: str) -> str:
    del business_object
    from config.backup_integrations import configured_due_backup_expiry_ids

    backup_ids = configured_due_backup_expiry_ids()
    for backup_id in backup_ids:
        expire_backup_task.delay(backup_id)
    return f"queued:{len(backup_ids)}"


def _task_response(result) -> dict[str, str]:
    if result.outcome == StartOutcome.ALREADY_SUCCEEDED:
        return {"status": "already_succeeded"}
    if result.result_ref.startswith("queued:"):
        return {"status": "queued"}
    return {
        "status": result.result_ref.rsplit(":", 1)[-1] if result.result_ref else "ok"
    }


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.operations.check_capacity",
)
def check_capacity(self) -> None:
    active_clock = SystemClock()
    window = _window_id(active_clock.now(), seconds=300)
    execute_celery_entry(
        self,
        task_name="apps.operations.check_capacity",
        business_object=_CAPACITY_SOURCE,
        idempotency_key=f"capacity:{window}",
        service=_capacity_service(active_clock),
    )


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.operations.check_service_health",
)
def check_service_health(self) -> None:
    active_clock = SystemClock()
    window = _window_id(active_clock.now(), seconds=60)
    execute_celery_entry(
        self,
        task_name="apps.operations.check_service_health",
        business_object=_HEALTH_SOURCE,
        idempotency_key=f"health:{window}",
        service=_health_service(active_clock),
    )


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=WEEKLY_BACKUP_TASK_NAME,
)
def weekly_backup_task(self) -> dict[str, str]:
    week_id = shanghai_backup_week()
    business_object = f"backup:{week_id}"
    result = execute_celery_entry(
        self,
        task_name=WEEKLY_BACKUP_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        heartbeat_service=_weekly_backup_service,
        lease_seconds=1_800,
    )
    return _task_response(result)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=EXPIRE_BACKUP_TASK_NAME,
)
def expire_backup_task(self, backup_id: str) -> dict[str, str]:
    identity = normalize_ulid(backup_id)
    business_object = f"backup:{identity}:expire"
    result = execute_celery_entry(
        self,
        task_name=EXPIRE_BACKUP_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_expire_backup_service,
    )
    return _task_response(result)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=BACKUP_EXPIRY_DISPATCH_TASK_NAME,
)
def dispatch_expired_backups_task(self) -> dict[str, str]:
    request_id = _request_id(self)
    business_object = f"backup-expiry-dispatch:{request_id}"
    result = execute_celery_entry(
        self,
        task_name=BACKUP_EXPIRY_DISPATCH_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_dispatch_expired_backup_service,
    )
    return _task_response(result)
