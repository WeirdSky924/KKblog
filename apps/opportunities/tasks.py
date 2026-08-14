from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from celery import shared_task

from apps.core.ids import normalize_ulid
from apps.operations.public import StartOutcome, execute_celery_entry

from .services.check_runs import (
    dispatch_pending_check_runs,
    request_scheduled_full_check,
)
from .services.run_execution import execute_check_run

RUN_CHECK_TASK_NAME = "apps.opportunities.run_check"
SCHEDULE_CHECK_TASK_NAME = "apps.opportunities.schedule_daily_check"
CLEANUP_CHECK_TASK_NAME = "apps.opportunities.cleanup_check_history"
DISPATCH_PENDING_CHECKS_TASK_NAME = "apps.opportunities.dispatch_pending_check_runs"


def dispatch_check_run(run_id: str) -> None:
    run_check_task.delay(normalize_ulid(run_id))


def _business_run_id(value: str) -> str:
    prefix = "opportunity-run:"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("Invalid opportunity check business object")
    return normalize_ulid(value[len(prefix) :])


def _execute_run_service(business_object: str, heartbeat) -> str:
    return execute_check_run(_business_run_id(business_object), heartbeat)


def _schedule_service(business_object: str) -> str:
    prefix = "opportunity-schedule:"
    if not isinstance(business_object, str) or not business_object.startswith(prefix):
        raise ValueError("Invalid opportunity schedule business object")
    window = business_object[len(prefix) :]
    datetime.strptime(window, "%Y-%m-%d").replace(tzinfo=UTC)
    result = request_scheduled_full_check(dispatcher=dispatch_check_run)
    return f"opportunity-run:{result.run_id}"


def _cleanup_service(business_object: str) -> str:
    prefix = "opportunity-cleanup:"
    if not isinstance(business_object, str) or not business_object.startswith(prefix):
        raise ValueError("Invalid opportunity cleanup business object")
    window = business_object[len(prefix) :]
    datetime.strptime(window, "%Y-%m-%d").replace(tzinfo=UTC)
    from .services.retention import cleanup_expired_check_history

    result = cleanup_expired_check_history()
    return f"opportunity-cleanup:{result.snapshots}:{result.checks}"


def _dispatch_pending_service(business_object: str) -> str:
    prefix = "opportunity-dispatch:"
    if not isinstance(business_object, str) or not business_object.startswith(prefix):
        raise ValueError("Invalid opportunity dispatch business object")
    window = business_object[len(prefix) :]
    datetime.strptime(window, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    count = dispatch_pending_check_runs(dispatcher=dispatch_check_run)
    return f"opportunity-dispatch:{count}"


def _request_uuid(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid opportunity task request ID") from None


def _response(result) -> dict[str, str]:
    return {
        "status": (
            "already_succeeded"
            if result.outcome == StartOutcome.ALREADY_SUCCEEDED
            else result.outcome.value
        ),
        "result_ref": result.result_ref,
    }


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=RUN_CHECK_TASK_NAME,
)
def run_check_task(self, run_id: str) -> dict[str, str]:
    identity = normalize_ulid(run_id)
    business_object = f"opportunity-run:{identity}"
    result = execute_celery_entry(
        self,
        task_name=RUN_CHECK_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        heartbeat_service=_execute_run_service,
        lease_seconds=86_400,
    )
    return _response(result)


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=SCHEDULE_CHECK_TASK_NAME,
)
def schedule_daily_check_task(self) -> dict[str, str]:
    request_id = _request_uuid(self)
    window = datetime.now(UTC).strftime("%Y-%m-%d")
    business_object = f"opportunity-schedule:{window}"
    result = execute_celery_entry(
        self,
        task_name=SCHEDULE_CHECK_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_schedule_service,
    )
    return {**_response(result), "request_id": request_id}


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=CLEANUP_CHECK_TASK_NAME,
)
def cleanup_check_history_task(self) -> dict[str, str]:
    _request_uuid(self)
    window = datetime.now(UTC).strftime("%Y-%m-%d")
    business_object = f"opportunity-cleanup:{window}"
    result = execute_celery_entry(
        self,
        task_name=CLEANUP_CHECK_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_cleanup_service,
    )
    return _response(result)


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=DISPATCH_PENDING_CHECKS_TASK_NAME,
)
def dispatch_pending_check_runs_task(self) -> dict[str, str]:
    _request_uuid(self)
    window = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
    business_object = f"opportunity-dispatch:{window}"
    result = execute_celery_entry(
        self,
        task_name=DISPATCH_PENDING_CHECKS_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_dispatch_pending_service,
    )
    return _response(result)


__all__ = [
    "cleanup_check_history_task",
    "dispatch_check_run",
    "dispatch_pending_check_runs_task",
    "run_check_task",
    "schedule_daily_check_task",
]
