import re
from collections.abc import Mapping

from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import is_ulid

_SAFE_ERROR = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_SOURCE_STATES = frozenset({"NEVER", "HEALTHY", "DEGRADED", "STALE", "UNSUPPORTED"})
_RUN_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "TRUNCATED", "CANCELLED"})


def _source_state_changed(payload: Mapping[str, object]) -> None:
    required = {"source_name", "previous_state", "current_state", "error_code"}
    source_name = payload.get("source_name")
    previous = payload.get("previous_state")
    current = payload.get("current_state")
    error_code = payload.get("error_code")
    if (
        set(payload) != required
        or not isinstance(source_name, str)
        or not 1 <= len(source_name) <= 120
        or previous not in _SOURCE_STATES
        or current not in _SOURCE_STATES
        or previous == current
        or not isinstance(error_code, str)
        or (error_code and not _SAFE_ERROR.fullmatch(error_code))
        or (current in {"DEGRADED", "STALE", "UNSUPPORTED"}) != bool(error_code)
    ):
        raise EventValidationError("Invalid opportunity source state payload")


def _check_summary(payload: Mapping[str, object]) -> None:
    required = {
        "state",
        "succeeded",
        "failed",
        "truncated",
        "skipped",
        "not_executed",
        "created",
        "changed",
        "missing",
        "job_failures",
    }
    if set(payload) != required or payload.get("state") not in _RUN_STATES:
        raise EventValidationError("Invalid opportunity check summary payload")
    for field in required - {"state"}:
        value = payload[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EventValidationError("Invalid opportunity check summary payload")


def _check_stalled(payload: Mapping[str, object]) -> None:
    required = {
        "run_id",
        "source_name",
        "source_position",
        "reason",
        "attempt",
        "final_failed",
        "max_duration_seconds",
    }
    if set(payload) != required:
        raise EventValidationError("Invalid opportunity stalled-check payload")
    source_name = payload["source_name"]
    source_position = payload["source_position"]
    attempt = payload["attempt"]
    max_duration = payload["max_duration_seconds"]
    if (
        not isinstance(payload["run_id"], str)
        or not is_ulid(payload["run_id"])
        or not isinstance(source_name, str)
        or not 1 <= len(source_name) <= 120
        or "<" in source_name
        or ">" in source_name
        or "://" in source_name
        or source_position is None
        or isinstance(source_position, bool)
        or not isinstance(source_position, int)
        or not 1 <= source_position <= 5_000
        or payload["reason"] not in {"LEASE_EXPIRED", "SOURCE_TIMEOUT"}
        or isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or not 0 <= attempt <= 3
        or type(payload["final_failed"]) is not bool
        or isinstance(max_duration, bool)
        or not isinstance(max_duration, int)
        or not 0 <= max_duration <= 600
        or (payload["reason"] == "LEASE_EXPIRED" and (attempt < 1 or max_duration != 0))
        or (
            payload["reason"] == "SOURCE_TIMEOUT"
            and (attempt != 0 or payload["final_failed"] or max_duration < 1)
        )
    ):
        raise EventValidationError("Invalid opportunity stalled-check payload")


SOURCE_STATE_CHANGED = EventDefinition(
    "opportunity.source_state_changed.v1",
    _source_state_changed,
)
CHECK_SUMMARY = EventDefinition(
    "opportunity.check_summary.v1",
    _check_summary,
)
CHECK_STALLED = EventDefinition(
    "opportunity.check_stalled.v1",
    _check_stalled,
)

__all__ = ["CHECK_STALLED", "CHECK_SUMMARY", "SOURCE_STATE_CHANGED"]
