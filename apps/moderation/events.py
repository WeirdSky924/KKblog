from collections.abc import Mapping
from uuid import UUID

from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import normalize_ulid

_REPORT_REASONS = {
    "SPAM",
    "HARASSMENT",
    "ILLEGAL_DANGEROUS",
    "PRIVACY",
    "IRRELEVANT",
    "OTHER",
}


def report_notification_description(value: str) -> str:
    """Keep report context readable without placing active markup or URLs in events."""
    if (
        not isinstance(value, str)
        or len(value) > 200
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in value
        )
    ):
        raise EventValidationError("Report notification description is invalid")
    return value.replace("://", "：//").replace("<", "＜").replace(">", "＞")


def _report_notification_context(payload: Mapping[str, object]) -> bool:
    reason = payload["reason"]
    description = payload["description"]
    return bool(
        isinstance(reason, str)
        and reason in _REPORT_REASONS
        and isinstance(description, str)
        and len(description) <= 200
        and "<" not in description
        and ">" not in description
        and "://" not in description
        and all(
            character.isprintable() or character in "\n\t" for character in description
        )
    )


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


def _report_reviewed_v2(payload: Mapping[str, object]) -> None:
    expected = {
        "target_comment_id",
        "reason",
        "description",
        "outcome",
        "decision_reason",
        "recipient_ids",
    }
    if set(payload) != expected:
        raise EventValidationError("Report review event payload shape is invalid")
    _report_reviewed(
        {
            key: payload[key]
            for key in (
                "target_comment_id",
                "outcome",
                "decision_reason",
                "recipient_ids",
            )
        }
    )
    if not _report_notification_context(payload):
        raise EventValidationError("Report review event payload shape is invalid")


REPORT_REVIEWED_V2 = EventDefinition("report.reviewed.v2", _report_reviewed_v2)


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


def _report_finalized_v2(payload: Mapping[str, object]) -> None:
    expected = {
        "target_comment_id",
        "reason",
        "description",
        "outcome",
        "basis_outcome",
        "decision_reason",
        "recipient_ids",
        "recovery_status",
    }
    if set(payload) != expected:
        raise EventValidationError("Report final event payload shape is invalid")
    _report_finalized(
        {
            key: payload[key]
            for key in (
                "target_comment_id",
                "outcome",
                "decision_reason",
                "recipient_ids",
                "recovery_status",
            )
        }
    )
    if payload["basis_outcome"] not in {
        "UPHELD",
        "REJECTED",
    } or not _report_notification_context(payload):
        raise EventValidationError("Report final event payload shape is invalid")


REPORT_FINALIZED_V2 = EventDefinition("report.finalized.v2", _report_finalized_v2)


def _recipient(value: object) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _safe_reason(value: object) -> bool:
    return (
        bool(
            isinstance(value, str)
            and len(value) <= 200
            and "<" not in value
            and ">" not in value
            and "://" not in value
            and all(
                character.isprintable() or character in "\n\t" for character in value
            )
        )
        or value == ""
    )


def _article_moderated(payload: Mapping[str, object]) -> None:
    if set(payload) != {"case_id", "action", "reason", "recipient_id"}:
        raise EventValidationError("Article moderation event payload shape is invalid")
    try:
        normalize_ulid(payload["case_id"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Article moderation event payload shape is invalid"
        ) from None
    if (
        payload["action"] not in {"HIDE", "DELETE"}
        or not _safe_reason(payload["reason"])
        or not _recipient(payload["recipient_id"])
    ):
        raise EventValidationError("Article moderation event payload shape is invalid")


ARTICLE_MODERATED = EventDefinition("article.moderated.v1", _article_moderated)


def _article_moderation_restored(payload: Mapping[str, object]) -> None:
    if set(payload) != {
        "case_id",
        "action",
        "recipient_id",
        "recovery_status",
    }:
        raise EventValidationError("Article restore event payload shape is invalid")
    try:
        normalize_ulid(payload["case_id"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Article restore event payload shape is invalid"
        ) from None
    if (
        payload["action"] not in {"HIDE", "DELETE"}
        or payload["recovery_status"] != "RESTORED"
        or not _recipient(payload["recipient_id"])
    ):
        raise EventValidationError("Article restore event payload shape is invalid")


ARTICLE_MODERATION_RESTORED = EventDefinition(
    "article.moderation_restored.v1",
    _article_moderation_restored,
)


def _article_moderation_finalized(payload: Mapping[str, object]) -> None:
    if set(payload) != {
        "case_id",
        "action",
        "outcome",
        "decision_reason",
        "recipient_id",
        "recovery_status",
    }:
        raise EventValidationError("Article final event payload shape is invalid")
    try:
        normalize_ulid(payload["case_id"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Article final event payload shape is invalid"
        ) from None
    if (
        payload["action"] not in {"HIDE", "DELETE"}
        or payload["outcome"] not in {"FINAL_UPHELD", "FINAL_REJECTED"}
        or payload["recovery_status"] not in {"NOT_REQUIRED", "RESTORED", "FAILED"}
        or not _safe_reason(payload["decision_reason"])
        or not _recipient(payload["recipient_id"])
    ):
        raise EventValidationError("Article final event payload shape is invalid")


ARTICLE_MODERATION_FINALIZED = EventDefinition(
    "article.moderation_finalized.v1",
    _article_moderation_finalized,
)


def _report_closed(payload: Mapping[str, object]) -> None:
    if set(payload) != {"target_comment_id", "outcome", "recipient_id"}:
        raise EventValidationError("Report closed event payload shape is invalid")
    try:
        normalize_ulid(payload["target_comment_id"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Report closed event payload shape is invalid"
        ) from None
    if payload["outcome"] != "CONTENT_DELETED" or not _recipient(
        payload["recipient_id"]
    ):
        raise EventValidationError("Report closed event payload shape is invalid")


REPORT_CLOSED = EventDefinition("report.closed.v1", _report_closed)
