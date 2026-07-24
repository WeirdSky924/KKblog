from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import normalize_ulid

from .targets import normalize_target


def _comment_created(payload: Mapping[str, object]) -> None:
    expected = {
        "thread_id",
        "target_type",
        "target_id",
        "author_kind",
        "visible_at",
        "image_count",
    }
    if set(payload) != expected:
        raise EventValidationError("Comment event payload shape is invalid")
    try:
        UUID(str(payload["thread_id"]))
        normalize_target(payload["target_type"], payload["target_id"])
        visible_at = datetime.fromisoformat(str(payload["visible_at"]))
    except (TypeError, ValueError):
        raise EventValidationError("Comment event payload shape is invalid") from None
    image_count = payload["image_count"]
    if (
        not isinstance(payload["target_id"], str)
        or not payload["target_id"]
        or payload["author_kind"] not in {"ANONYMOUS", "ACCOUNT"}
        or visible_at.tzinfo is None
        or isinstance(image_count, bool)
        or not isinstance(image_count, int)
        or not 0 <= image_count <= 3
    ):
        raise EventValidationError("Comment event payload shape is invalid")


COMMENT_CREATED = EventDefinition("comment.created.v1", _comment_created)


def _comment_deep_thread(payload: Mapping[str, object]) -> None:
    expected = {
        "thread_id",
        "target_type",
        "target_id",
        "owner_id",
        "root_id",
        "depth",
    }
    if set(payload) != expected:
        raise EventValidationError("Deep thread event payload shape is invalid")
    try:
        UUID(str(payload["thread_id"]))
        UUID(str(payload["owner_id"]))
        normalize_target(payload["target_type"], payload["target_id"])
        normalize_ulid(payload["root_id"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Deep thread event payload shape is invalid"
        ) from None
    depth = payload["depth"]
    if isinstance(depth, bool) or not isinstance(depth, int) or depth <= 100:
        raise EventValidationError("Deep thread event payload shape is invalid")


COMMENT_DEEP_THREAD = EventDefinition(
    "comment.deep_thread.v1",
    _comment_deep_thread,
)


def _comment_deleted(payload: Mapping[str, object]) -> None:
    expected = {
        "thread_id",
        "target_type",
        "target_id",
        "comment_id",
        "deleted_by_kind",
        "recipient_ids",
        "reason",
    }
    if set(payload) != expected:
        raise EventValidationError("Comment deletion event payload shape is invalid")
    try:
        UUID(str(payload["thread_id"]))
        normalize_target(payload["target_type"], payload["target_id"])
        normalize_ulid(payload["comment_id"])
        recipients = tuple(UUID(str(value)) for value in payload["recipient_ids"])
    except (TypeError, ValueError):
        raise EventValidationError(
            "Comment deletion event payload shape is invalid"
        ) from None
    reason = payload["reason"]
    if (
        payload["deleted_by_kind"] not in {"SELF", "OWNER", "ADMIN"}
        or not isinstance(payload["recipient_ids"], list)
        or len(recipients) > 2
        or len(set(recipients)) != len(recipients)
        or (reason is not None and (not isinstance(reason, str) or not reason))
        or (isinstance(reason, str) and len(reason) > 200)
        or (
            payload["deleted_by_kind"] != "ADMIN" and (recipients or reason is not None)
        )
    ):
        raise EventValidationError("Comment deletion event payload shape is invalid")


COMMENT_DELETED = EventDefinition("comment.deleted.v1", _comment_deleted)
