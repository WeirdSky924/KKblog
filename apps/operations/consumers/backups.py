from apps.core.events import EventEnvelope, consume_once
from apps.core.time.clock import Clock, SystemClock
from apps.operations.backup_storage import BackupStorage
from apps.operations.services.backup import mark_backup_task_final_failed

from .final_failures import validate_task_final_failure

CONSUMER_NAME = "operations.backup-final-failure.v1"
TASK_NAME = "apps.operations.weekly_backup"


def _week_id(business_object: str) -> str:
    prefix, separator, week_id = business_object.partition(":")
    if prefix != "backup" or separator != ":" or not week_id:
        raise ValueError("Invalid backup task business object")
    return week_id


def consume_backup_task_final_failure(
    envelope: EventEnvelope,
    *,
    storage: BackupStorage,
    clock: Clock | None = None,
):
    if envelope.payload.get("task_name") != TASK_NAME:
        return None
    active_clock = clock or SystemClock()

    def handle(item: EventEnvelope) -> None:
        run, payload = validate_task_final_failure(item)
        week_id = _week_id(run.business_object)
        if run.idempotency_key != run.business_object or payload["attempt"] != 3:
            raise ValueError("Invalid backup task failure event")
        mark_backup_task_final_failed(
            week_id=week_id,
            error_code=run.last_error_code,
            storage=storage,
            clock=active_clock,
        )

    return consume_once(
        envelope,
        CONSUMER_NAME,
        handle,
        clock=active_clock,
    )
