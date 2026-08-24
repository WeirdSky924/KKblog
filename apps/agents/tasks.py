from celery import shared_task
from django.utils import timezone

from apps.agents.gateway import build_agent_gateway
from apps.agents.services.checks import (
    execute_agent_endpoint_check,
    mark_agent_endpoint_check_final_failed,
)
from apps.core.ids import normalize_ulid
from apps.operations.public import (
    TaskFinalFailed,
    current_task_run_id,
    execute_celery_entry,
)

CHECK_ENDPOINT_TASK_NAME = "apps.agents.check_endpoint"


def dispatch_endpoint_check(check_id: str) -> None:
    check_endpoint_task.delay(normalize_ulid(check_id))


def _check_id(business_object: str) -> str:
    prefix = "agent-check:"
    if not isinstance(business_object, str) or not business_object.startswith(prefix):
        raise ValueError("Invalid agent endpoint check business object")
    return normalize_ulid(business_object[len(prefix) :])


def _execute_check_service(business_object: str) -> str:
    check_id = _check_id(business_object)
    task_run_id = current_task_run_id()
    if task_run_id is None:
        raise ValueError("Agent endpoint check has no TaskRun")
    result = execute_agent_endpoint_check(
        check_id=check_id,
        task_run_id=task_run_id,
        gateway=build_agent_gateway(),
    )
    return f"agent-check:{result.id}:{result.state.casefold()}"


@shared_task(
    bind=True,
    ignore_result=False,
    max_retries=None,
    name=CHECK_ENDPOINT_TASK_NAME,
)
def check_endpoint_task(self, check_id: str) -> dict[str, str]:
    identity = normalize_ulid(check_id)
    business_object = f"agent-check:{identity}"
    try:
        result = execute_celery_entry(
            self,
            task_name=CHECK_ENDPOINT_TASK_NAME,
            business_object=business_object,
            idempotency_key=business_object,
            service=_execute_check_service,
            lease_seconds=3_600,
        )
    except TaskFinalFailed as error:
        mark_agent_endpoint_check_final_failed(
            check_id=identity,
            safe_error_code=error.error_code,
            completed_at=timezone.now(),
        )
        raise
    return {"status": result.outcome.value, "result_ref": result.result_ref}


__all__ = ["check_endpoint_task", "dispatch_endpoint_check"]
