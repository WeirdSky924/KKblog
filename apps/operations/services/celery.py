from collections.abc import Callable

from celery import Task

from .tasks import (
    TaskFinalFailed,
    TaskRetryScheduled,
    TaskStartResult,
    execute_tracked_task,
)


def execute_celery_entry(
    celery_task: Task,
    *,
    task_name: str,
    business_object: str,
    idempotency_key: str,
    service: Callable[[str], str | None],
) -> TaskStartResult:
    request_id = getattr(celery_task.request, "id", None)
    if not isinstance(request_id, str) or not request_id:
        raise TaskFinalFailed(error_code="operations.task_request_invalid.v1")
    try:
        return execute_tracked_task(
            task_name=task_name,
            business_object=business_object,
            idempotency_key=idempotency_key,
            celery_id=request_id,
            service=service,
        )
    except TaskRetryScheduled as scheduled:
        raise celery_task.retry(
            exc=TaskRetryScheduled(
                countdown=scheduled.countdown,
                error_code=scheduled.error_code,
            ),
            countdown=scheduled.countdown,
        ) from None
