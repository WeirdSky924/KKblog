from uuid import UUID

from celery import shared_task

from apps.core.ids import normalize_ulid
from apps.exchange.public import ExportBuildRetryable
from apps.operations.public import (
    RetryableTaskError,
    StartOutcome,
    execute_celery_entry,
)

BUILD_TASK_NAME = "apps.exchange.build_export"
EXPIRE_TASK_NAME = "apps.exchange.expire_export"
EXPIRY_DISPATCH_TASK_NAME = "apps.exchange.dispatch_expired_exports"


def _job_id(business_object: str, *, suffix: str = "") -> str:
    prefix = "export:"
    expected_suffix = f":{suffix}" if suffix else ""
    if (
        not isinstance(business_object, str)
        or not business_object.startswith(prefix)
        or not business_object.endswith(expected_suffix)
    ):
        raise ValueError("Invalid export business object")
    raw = business_object[len(prefix) :]
    if suffix:
        raw = raw[: -len(expected_suffix)]
    return normalize_ulid(raw)


def _build_service(business_object: str, heartbeat) -> str:
    from config.exchange_integrations import build_configured_export

    job_id = _job_id(business_object)
    try:
        result = build_configured_export(job_id, heartbeat=heartbeat)
    except ExportBuildRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"export:{job_id}:{result.state.lower()}"


def _expire_service(business_object: str) -> str:
    from config.exchange_integrations import expire_configured_export

    job_id = _job_id(business_object, suffix="expire")
    try:
        result = expire_configured_export(job_id)
    except ExportBuildRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"export:{job_id}:{result.state.lower()}"


def _response(result) -> dict[str, str]:
    if result.outcome == StartOutcome.ALREADY_SUCCEEDED:
        return {"status": "already_succeeded"}
    if result.result_ref.startswith("queued:"):
        return {"status": "queued"}
    return {
        "status": result.result_ref.rsplit(":", 1)[-1] if result.result_ref else "ok"
    }


def _request_id(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid export expiry dispatcher request ID") from None


def _dispatch_expired_service(business_object: str) -> str:
    del business_object
    from config.exchange_integrations import configured_due_export_expiry_ids

    job_ids = configured_due_export_expiry_ids()
    for job_id in job_ids:
        expire_export_task.delay(job_id)
    return f"queued:{len(job_ids)}"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=BUILD_TASK_NAME,
)
def build_export_task(self, job_id: str) -> dict[str, str]:
    identity = normalize_ulid(job_id)
    business_object = f"export:{identity}"
    result = execute_celery_entry(
        self,
        task_name=BUILD_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        heartbeat_service=_build_service,
        lease_seconds=600,
    )
    return _response(result)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=EXPIRE_TASK_NAME,
)
def expire_export_task(self, job_id: str) -> dict[str, str]:
    identity = normalize_ulid(job_id)
    business_object = f"export:{identity}:expire"
    result = execute_celery_entry(
        self,
        task_name=EXPIRE_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_expire_service,
    )
    return _response(result)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=EXPIRY_DISPATCH_TASK_NAME,
)
def dispatch_expired_exports_task(self) -> dict[str, str]:
    request_id = _request_id(self)
    business_object = f"export-expiry-dispatch:{request_id}"
    result = execute_celery_entry(
        self,
        task_name=EXPIRY_DISPATCH_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_dispatch_expired_service,
    )
    return _response(result)
