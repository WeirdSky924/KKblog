from celery import shared_task

from apps.core.ids import normalize_ulid
from apps.exchange.public import ImportProcessingRetryable
from apps.operations.public import (
    RetryableTaskError,
    StartOutcome,
    execute_celery_entry,
)


def _business_object(job_id: str, preview_version: int) -> str:
    identity = normalize_ulid(job_id)
    if (
        isinstance(preview_version, bool)
        or not isinstance(preview_version, int)
        or preview_version < 1
    ):
        raise ValueError("Invalid import preview version")
    return f"import:{identity}:{preview_version}"


def _parse_business_object(value: str) -> tuple[str, int]:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "import":
        raise ValueError("Invalid import business object")
    try:
        version = int(parts[2])
    except ValueError:
        raise ValueError("Invalid import business object") from None
    return normalize_ulid(parts[1]), version


def _process_service(business_object: str) -> str:
    from config.exchange_integrations import process_configured_import_job

    job_id, version = _parse_business_object(business_object)
    try:
        result = process_configured_import_job(job_id, version)
    except ImportProcessingRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"import:{job_id}:{result.status.lower()}"


def _task_response(result) -> dict[str, str]:
    if result.outcome == StartOutcome.ALREADY_SUCCEEDED:
        status = "already_succeeded"
    else:
        status = result.result_ref.rsplit(":", 1)[-1] if result.result_ref else "ok"
    return {"status": status}


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.exchange.process_import_job",
)
def process_import_job_task(
    self,
    job_id: str,
    preview_version: int,
) -> dict[str, str]:
    business_object = _business_object(job_id, preview_version)
    result = execute_celery_entry(
        self,
        task_name="apps.exchange.process_import_job",
        business_object=business_object,
        idempotency_key=business_object,
        service=_process_service,
    )
    return _task_response(result)
