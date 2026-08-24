from datetime import datetime

from celery import shared_task
from django.utils import timezone

from apps.learning.services.cleanup import cleanup_learning_expired
from apps.operations.public import execute_celery_entry

LEARNING_CLEANUP_TASK_NAME = "apps.learning.cleanup_expired_learning"


def _window(moment: datetime) -> str:
    epoch = int(moment.timestamp())
    return str(epoch - epoch % 3_600)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=LEARNING_CLEANUP_TASK_NAME,
)
def cleanup_expired_learning(self) -> dict[str, object]:
    current = timezone.now()
    window = _window(current)
    result = execute_celery_entry(
        self,
        task_name=LEARNING_CLEANUP_TASK_NAME,
        business_object="learning-cleanup",
        idempotency_key=f"learning-cleanup:{window}",
        service=lambda _business_object: (
            f"learning-cleanup:{cleanup_learning_expired(now=current).documents_deleted}"
        ),
    )
    return {"status": result.outcome.value, "result_ref": result.result_ref}


__all__ = ["LEARNING_CLEANUP_TASK_NAME", "cleanup_expired_learning"]
