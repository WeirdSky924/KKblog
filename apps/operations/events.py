import re
from collections.abc import Mapping

from apps.core.events.envelope import EventDefinition, EventValidationError

_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:_.-]{0,254}\Z")
_SOURCE_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_CAPACITY_STATES = frozenset({"unknown", "normal", "warn", "no_image", "read_only"})
_HEALTH_STATES = frozenset({"unknown", "healthy", "unavailable"})


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


def _validate_state_change(
    payload: Mapping[str, object],
    *,
    states: frozenset[str],
) -> None:
    if set(payload) != {"source_key", "previous_state", "current_state"}:
        raise EventValidationError("Invalid operational state change payload")
    source_key = payload["source_key"]
    previous_state = payload["previous_state"]
    current_state = payload["current_state"]
    if (
        not isinstance(source_key, str)
        or not _SOURCE_KEY.fullmatch(source_key)
        or previous_state not in states
        or current_state not in states - {"unknown"}
        or previous_state == current_state
    ):
        raise EventValidationError("Invalid operational state change payload")


def _validate_capacity_change(payload: Mapping[str, object]) -> None:
    _validate_state_change(payload, states=_CAPACITY_STATES)


def _validate_health_change(payload: Mapping[str, object]) -> None:
    _validate_state_change(payload, states=_HEALTH_STATES)


CAPACITY_THRESHOLD_CHANGED = EventDefinition(
    "capacity.threshold_changed.v1",
    _validate_capacity_change,
)

SERVICE_HEALTH_CHANGED = EventDefinition(
    "service.health_changed.v1",
    _validate_health_change,
)
