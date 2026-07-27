from apps.core.events import EventEnvelope, consume_once
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock

from ..archive_storage import ExportArchiveStorage
from ..services.export_lifecycle import mark_export_task_final_failed

CONSUMER_NAME = "exchange.export-final-failure.v1"
TASK_NAME = "apps.exchange.build_export"


class ExportTaskFailureEventError(ValueError):
    pass


def _payload(envelope: EventEnvelope) -> tuple[str, str]:
    expected = {
        "task_name",
        "business_object",
        "idempotency_key",
        "attempt",
        "error_code",
    }
    if (
        not isinstance(envelope, EventEnvelope)
        or envelope.event_type != "task.final_failed.v1"
        or envelope.schema_version != 1
        or envelope.aggregate_type != "task_run"
        or set(envelope.payload) != expected
        or envelope.payload["task_name"] != TASK_NAME
        or envelope.payload["attempt"] != 3
    ):
        raise ExportTaskFailureEventError("Invalid export task failure event")
    business_object = envelope.payload["business_object"]
    if (
        not isinstance(business_object, str)
        or not business_object.startswith("export:")
        or envelope.payload["idempotency_key"] != business_object
    ):
        raise ExportTaskFailureEventError("Invalid export task failure event")
    try:
        job_id = normalize_ulid(business_object.removeprefix("export:"))
    except (TypeError, ValueError):
        raise ExportTaskFailureEventError("Invalid export task failure event") from None
    error_code = envelope.payload["error_code"]
    if not isinstance(error_code, str):
        raise ExportTaskFailureEventError("Invalid export task failure event")
    return job_id, error_code


def consume_export_task_final_failure(
    envelope: EventEnvelope,
    *,
    storage: ExportArchiveStorage,
    clock: Clock | None = None,
):
    job_id, error_code = _payload(envelope)
    active_clock = clock or SystemClock()
    return consume_once(
        envelope,
        CONSUMER_NAME,
        lambda item: mark_export_task_final_failed(
            job_id=job_id,
            error_code=error_code,
            storage=storage,
            clock=active_clock,
        ),
        clock=active_clock,
    )
