import re
from collections.abc import Mapping
from uuid import UUID

from apps.core.events import EventDefinition, EventValidationError

_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")


def _review_terminal(payload: Mapping[str, object]) -> None:
    if set(payload) != {"recipient_id"}:
        raise EventValidationError("Invalid learning review event")
    try:
        UUID(str(payload["recipient_id"]))
    except (TypeError, ValueError):
        raise EventValidationError("Invalid learning review recipient") from None


def _administration_change(payload: Mapping[str, object]) -> None:
    if set(payload) != {"recipient_id", "action"}:
        raise EventValidationError("Invalid learning administration event")
    try:
        UUID(str(payload["recipient_id"]))
    except (TypeError, ValueError):
        raise EventValidationError(
            "Invalid learning administration recipient"
        ) from None
    if payload["action"] not in {"HIDE", "RESTORE", "DELETE"}:
        raise EventValidationError("Invalid learning administration action")


def _generation_failed(payload: Mapping[str, object]) -> None:
    if frozenset(payload) not in (
        frozenset({"recipient_id"}),
        frozenset({"recipient_id", "error_code"}),
    ):
        raise EventValidationError("Invalid learning generation failure event")
    try:
        UUID(str(payload["recipient_id"]))
    except (TypeError, ValueError):
        raise EventValidationError("Invalid learning generation recipient") from None
    if "error_code" in payload and (
        not isinstance(payload["error_code"], str)
        or _ERROR_CODE.fullmatch(payload["error_code"]) is None
    ):
        raise EventValidationError("Invalid learning generation error code")


REVIEW_APPROVED = EventDefinition("learning.review_approved.v1", _review_terminal)
REVIEW_REJECTED = EventDefinition("learning.review_rejected.v1", _review_terminal)
REVIEW_FAILED = EventDefinition("learning.review_failed.v1", _review_terminal)
GENERATION_COMPLETED = EventDefinition(
    "learning.generation_completed.v1",
    _review_terminal,
)
GENERATION_PARTIAL = EventDefinition(
    "learning.generation_partial.v1",
    _review_terminal,
)
GENERATION_FAILED = EventDefinition(
    "learning.generation_failed.v1",
    _generation_failed,
)
APPEAL_APPROVED = EventDefinition("learning.appeal_approved.v1", _review_terminal)
APPEAL_REJECTED = EventDefinition("learning.appeal_rejected.v1", _review_terminal)
DOCUMENT_ADMINISTRATION_CHANGED = EventDefinition(
    "learning.document_administration_changed.v1",
    _administration_change,
)
QUESTION_BANK_ADMINISTRATION_CHANGED = EventDefinition(
    "learning.question_bank_administration_changed.v1",
    _administration_change,
)

__all__ = [
    "APPEAL_APPROVED",
    "APPEAL_REJECTED",
    "DOCUMENT_ADMINISTRATION_CHANGED",
    "GENERATION_COMPLETED",
    "GENERATION_FAILED",
    "GENERATION_PARTIAL",
    "QUESTION_BANK_ADMINISTRATION_CHANGED",
    "REVIEW_APPROVED",
    "REVIEW_FAILED",
    "REVIEW_REJECTED",
]
