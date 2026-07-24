from collections.abc import Mapping
from uuid import UUID

from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import normalize_ulid


def _report_reviewed(payload: Mapping[str, object]) -> None:
    expected = {
        "target_comment_id",
        "outcome",
        "decision_reason",
        "recipient_ids",
    }
    if set(payload) != expected:
        raise EventValidationError("Report review event payload shape is invalid")
    try:
        normalize_ulid(payload["target_comment_id"])
        recipients = tuple(UUID(str(value)) for value in payload["recipient_ids"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Report review event payload shape is invalid"
        ) from None
    reason = payload["decision_reason"]
    if (
        payload["outcome"] not in {"UPHELD", "REJECTED"}
        or not isinstance(reason, str)
        or len(reason) > 200
        or "<" in reason
        or ">" in reason
        or "://" in reason
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in reason
        )
        or not isinstance(payload["recipient_ids"], list)
        or not 1 <= len(recipients) <= 2
        or len(set(recipients)) != len(recipients)
    ):
        raise EventValidationError("Report review event payload shape is invalid")


REPORT_REVIEWED = EventDefinition("report.reviewed.v1", _report_reviewed)


def _report_finalized(payload: Mapping[str, object]) -> None:
    expected = {
        "target_comment_id",
        "outcome",
        "decision_reason",
        "recipient_ids",
        "recovery_status",
    }
    if set(payload) != expected:
        raise EventValidationError("Report final event payload shape is invalid")
    try:
        normalize_ulid(payload["target_comment_id"])
        recipients = tuple(UUID(str(value)) for value in payload["recipient_ids"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Report final event payload shape is invalid"
        ) from None
    reason = payload["decision_reason"]
    if (
        payload["outcome"] not in {"FINAL_UPHELD", "FINAL_REJECTED"}
        or payload["recovery_status"] not in {"NOT_REQUIRED", "RESTORED", "FAILED"}
        or not isinstance(reason, str)
        or len(reason) > 200
        or "<" in reason
        or ">" in reason
        or "://" in reason
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in reason
        )
        or not isinstance(payload["recipient_ids"], list)
        or not 1 <= len(recipients) <= 2
        or len(set(recipients)) != len(recipients)
    ):
        raise EventValidationError("Report final event payload shape is invalid")


REPORT_FINALIZED = EventDefinition("report.finalized.v1", _report_finalized)
