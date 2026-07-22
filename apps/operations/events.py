import re
from collections.abc import Mapping

from apps.core.events.envelope import EventDefinition, EventValidationError

_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_.-]{0,254}\Z")


def _validate_final_failure(payload: Mapping[str, object]) -> None:
    required = {
        "task_name",
        "business_object",
        "idempotency_key",
        "attempt",
        "error_code",
    }
    if set(payload) != required:
        raise EventValidationError("Invalid task.final_failed payload")
    for field in ("task_name", "business_object", "idempotency_key"):
        value = payload[field]
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise EventValidationError("Invalid task.final_failed payload")
    attempt = payload["attempt"]
    if (
        isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or not 1 <= attempt <= 3
    ):
        raise EventValidationError("Invalid task.final_failed payload")
    error_code = payload["error_code"]
    if not isinstance(error_code, str) or not _SAFE_CODE.fullmatch(error_code):
        raise EventValidationError("Invalid task.final_failed payload")


TASK_FINAL_FAILED = EventDefinition(
    "task.final_failed.v1",
    _validate_final_failure,
)
