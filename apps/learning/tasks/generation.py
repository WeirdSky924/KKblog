from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.agents.public import build_agent_gateway
from apps.learning.services.generation_runtime import (
    execute_question_bank_generation,
    mark_question_bank_generation_final_failed,
)
from apps.media.storage import FilesystemMediaStorage
from apps.operations.public import (
    TaskFinalFailed,
    current_task_run_id,
    execute_celery_entry,
)

QUESTION_GENERATION_TASK_NAME = "apps.learning.generate_question_bank"


def dispatch_question_generation(series_id: str) -> None:
    generate_question_bank_task.delay(str(UUID(str(series_id))))


def _series_id(business_object: str) -> UUID:
    prefix = "question-generation:"
    if not isinstance(business_object, str) or not business_object.startswith(prefix):
        raise ValueError("Invalid question generation business object")
    try:
        return UUID(business_object[len(prefix) :])
    except ValueError:
        raise ValueError("Invalid question generation business object") from None


def _execute_generation_service(business_object: str, renew_lease) -> str:
    series_id = _series_id(business_object)
    task_run_id = current_task_run_id()
    if task_run_id is None:
        raise ValueError("Question generation has no TaskRun")
    result = execute_question_bank_generation(
        series_id=series_id,
        task_run_id=task_run_id,
        gateway=build_agent_gateway(),
        renew_lease=renew_lease,
        storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
    )
    return f"question-generation:{result.series_id}:{result.state.casefold()}"


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=QUESTION_GENERATION_TASK_NAME,
)
def generate_question_bank_task(self, series_id: str) -> dict[str, str]:
    identity = UUID(str(series_id))
    business_object = f"question-generation:{identity}"
    try:
        result = execute_celery_entry(
            self,
            task_name=QUESTION_GENERATION_TASK_NAME,
            business_object=business_object,
            idempotency_key=business_object,
            heartbeat_service=_execute_generation_service,
            lease_seconds=3_600,
        )
    except TaskFinalFailed as error:
        mark_question_bank_generation_final_failed(
            series_id=identity,
            safe_error_code=error.error_code,
            completed_at=timezone.now(),
        )
        raise
    return {"status": result.outcome.value, "result_ref": result.result_ref}


__all__ = [
    "QUESTION_GENERATION_TASK_NAME",
    "dispatch_question_generation",
    "generate_question_bank_task",
]
