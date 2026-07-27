from datetime import date

from celery import shared_task

from apps.analytics.services.retention import (
    UmamiRetentionError,
    shanghai_retention_date,
)
from apps.operations.public import (
    RetryableTaskError,
    StartOutcome,
    execute_celery_entry,
)

EXPIRE_UMAMI_DATA_TASK_NAME = "apps.analytics.expire_umami_data"


def _retention_date_from_business_object(value: str) -> date:
    prefix, separator, raw_date = value.partition(":")
    if prefix != "umami-retention" or separator != ":":
        raise ValueError("Invalid Umami retention business object")
    try:
        parsed = date.fromisoformat(raw_date)
    except ValueError:
        raise ValueError("Invalid Umami retention business object") from None
    if parsed.isoformat() != raw_date:
        raise ValueError("Invalid Umami retention business object")
    return parsed


def _retention_service(business_object: str) -> str:
    _retention_date_from_business_object(business_object)
    from config.analytics_integrations import expire_configured_umami_data

    try:
        result = expire_configured_umami_data()
    except UmamiRetentionError as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"umami-retention:{result.counts.total}"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=EXPIRE_UMAMI_DATA_TASK_NAME,
)
def expire_umami_data_task(self) -> dict[str, str | int]:
    retention_date = shanghai_retention_date()
    business_object = f"umami-retention:{retention_date.isoformat()}"
    result = execute_celery_entry(
        self,
        task_name=EXPIRE_UMAMI_DATA_TASK_NAME,
        business_object=business_object,
        idempotency_key=business_object,
        service=_retention_service,
    )
    if result.outcome == StartOutcome.ALREADY_SUCCEEDED:
        return {"status": "already_succeeded"}
    count = int(result.result_ref.rsplit(":", 1)[-1])
    return {"status": "completed", "deleted": count}
