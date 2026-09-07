from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.agents.public import build_agent_gateway
from apps.learning.services.review_runtime import (
    execute_knowledge_review,
    mark_knowledge_review_final_failed,
)
from apps.media.storage import FilesystemMediaStorage
from apps.operations.public import (
    TaskFinalFailed,
    current_task_run_id,
    execute_celery_entry,
)

REVIEW_DOCUMENT_TASK_NAME = "apps.learning.review_knowledge_document"


def dispatch_knowledge_review(review_run_id: str) -> None:
    review_document_task.delay(str(UUID(str(review_run_id))))


def _review_id(business_object: str) -> UUID:
    prefix = "knowledge-review:"
    if not isinstance(business_object, str) or not business_object.startswith(prefix):
        raise ValueError("Invalid knowledge review business object")
    try:
        return UUID(business_object[len(prefix) :])
    except ValueError:
        raise ValueError("Invalid knowledge review business object") from None


def _execute_review_service(business_object: str, renew_lease) -> str:
    review_run_id = _review_id(business_object)
    task_run_id = current_task_run_id()
    if task_run_id is None:
        raise ValueError("Knowledge review has no TaskRun")
    result = execute_knowledge_review(
        review_run_id=review_run_id,
        task_run_id=task_run_id,
        gateway=build_agent_gateway(),
        renew_lease=renew_lease,
        storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
    )
    return f"knowledge-review:{result.review_run_id}:{result.document_state.casefold()}"


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=REVIEW_DOCUMENT_TASK_NAME,
)
def review_document_task(self, review_run_id: str) -> dict[str, str]:
    identity = UUID(str(review_run_id))
    business_object = f"knowledge-review:{identity}"
    try:
        result = execute_celery_entry(
            self,
            task_name=REVIEW_DOCUMENT_TASK_NAME,
            business_object=business_object,
            idempotency_key=business_object,
            heartbeat_service=_execute_review_service,
            # The gateway may perform up to three 30-minute provider attempts.
            lease_seconds=7_200,
        )
    except TaskFinalFailed as error:
        mark_knowledge_review_final_failed(
            review_run_id=identity,
            safe_error_code=error.error_code,
            completed_at=timezone.now(),
        )
        raise
    return {"status": result.outcome.value, "result_ref": result.result_ref}


__all__ = [
    "REVIEW_DOCUMENT_TASK_NAME",
    "dispatch_knowledge_review",
    "review_document_task",
]
