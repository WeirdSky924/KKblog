from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from celery import shared_task
from django.conf import settings

from apps.core.observability.context import current_trace_code
from apps.core.time.clock import Clock, SystemClock
from apps.operations.services.capacity import filesystem_capacity_sample
from apps.operations.services.celery import execute_celery_entry
from apps.operations.services.health import application_is_ready
from apps.operations.services.monitoring import (
    record_capacity_sample,
    sample_service_health,
)
from apps.operations.services.tasks import RetryableTaskError

_CAPACITY_SOURCE = "media_disk"
_HEALTH_SOURCE = "application"


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
