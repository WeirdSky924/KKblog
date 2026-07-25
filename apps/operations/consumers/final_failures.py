from apps.core.events import EventEnvelope, consume_once
from apps.core.time.clock import Clock
from apps.operations.events import TASK_FINAL_FAILED
from apps.operations.models import TaskRun, TaskRunStatus
from apps.operations.services.alerts import (
    AlertPersistenceError,
    record_task_final_failure_alert,
)

CONSUMER_NAME = "operations.task-final-failure-alert.v1"


def _handle(envelope: EventEnvelope, *, clock: Clock | None) -> None:
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.event_type != TASK_FINAL_FAILED.event_type
        or envelope.schema_version != TASK_FINAL_FAILED.schema_version
        or envelope.aggregate_type != "task_run"
    ):
        raise AlertPersistenceError("Invalid task final failure event")
    payload = TASK_FINAL_FAILED.validate_payload(dict(envelope.payload))
    run = TaskRun.objects.select_for_update().filter(pk=envelope.aggregate_id).first()
    if run is None or run.status != TaskRunStatus.FINAL_FAILED:
        raise AlertPersistenceError("Task final failure has no matching task run")
    expected = {
        "task_name": run.task_name,
        "business_object": run.business_object,
        "idempotency_key": run.idempotency_key,
        "attempt": run.attempt,
        "error_code": run.last_error_code,
    }
    if payload != expected or envelope.trace_code != run.trace_code:
        raise AlertPersistenceError("Task final failure event does not match task run")
    record_task_final_failure_alert(
        run,
        trace_code=envelope.trace_code,
        occurred_at=envelope.occurred_at,
    )


def consume_task_final_failure_alert(
    envelope: EventEnvelope,
    *,
    lease_seconds: int = 60,
    retry_delay_seconds: int = 60,
    clock: Clock | None = None,
):
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: _handle(item, clock=clock),
        lease_seconds=lease_seconds,
        retry_delay_seconds=retry_delay_seconds,
        clock=clock,
    )
