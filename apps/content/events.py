from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from apps.core.events import EventDefinition, EventValidationError
from apps.core.ids import is_ulid


def _section_changed(payload: Mapping[str, object]) -> None:
    if set(payload) != {"action"} or payload["action"] not in {
        "created",
        "renamed",
        "deleted",
    }:
        raise EventValidationError("Section event payload shape is invalid")


SECTION_CHANGED = EventDefinition("section.changed.v1", _section_changed)


def _recipient(value: object) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _tag_reviewed(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"outcome", "recipient_id"}
        or payload["outcome"] not in {"approved", "rejected"}
        or not _recipient(payload["recipient_id"])
    ):
        raise EventValidationError("Tag event payload shape is invalid")


def _tag_changed(payload: Mapping[str, object]) -> None:
    if set(payload) != {"action"} or payload["action"] not in {
        "created",
        "approved",
        "rejected",
        "deleted",
        "restored",
    }:
        raise EventValidationError("Tag event payload shape is invalid")


def _tag_restore_conflict(payload: Mapping[str, object]) -> None:
    if set(payload) != {"article_id", "recipient_id"} or not all(
        (
            isinstance(payload["article_id"], str),
            _recipient(payload["recipient_id"]),
        )
    ):
        raise EventValidationError("Tag conflict payload shape is invalid")


TAG_REVIEWED = EventDefinition("tag.reviewed.v1", _tag_reviewed)
TAG_CHANGED = EventDefinition("tag.changed.v1", _tag_changed)
TAG_RESTORE_CONFLICT = EventDefinition("tag.restore_conflict.v1", _tag_restore_conflict)


def _article_published(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"revision_id", "first"}
        or not isinstance(payload["revision_id"], str)
        or not is_ulid(payload["revision_id"])
        or type(payload["first"]) is not bool
    ):
        raise EventValidationError("Article event payload shape is invalid")


ARTICLE_PUBLISHED = EventDefinition("article.published.v1", _article_published)


def _article_scheduled(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"revision_id", "scheduled_for"}
        or not isinstance(payload["revision_id"], str)
        or not is_ulid(payload["revision_id"])
        or not isinstance(payload["scheduled_for"], str)
    ):
        raise EventValidationError("Article schedule payload shape is invalid")


def _article_schedule_cancelled(payload: Mapping[str, object]) -> None:
    if set(payload) != {"revision_id"} or (
        payload["revision_id"] is not None
        and (
            not isinstance(payload["revision_id"], str)
            or not is_ulid(payload["revision_id"])
        )
    ):
        raise EventValidationError("Article schedule payload shape is invalid")


ARTICLE_SCHEDULED = EventDefinition("article.scheduled.v1", _article_scheduled)
ARTICLE_SCHEDULE_CANCELLED = EventDefinition(
    "article.schedule_cancelled.v1", _article_schedule_cancelled
)


def _article_admin_viewed(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"recipient_id", "view_date"}
        or not _recipient(payload["recipient_id"])
        or not isinstance(payload["view_date"], str)
    ):
        raise EventValidationError("Article admin view payload shape is invalid")


def _article_visibility_changed(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"revision_id", "from", "to"}
        or not isinstance(payload["revision_id"], str)
        or not is_ulid(payload["revision_id"])
        or payload["from"] not in {"PUBLIC", "AUTHENTICATED", "PRIVATE"}
        or payload["to"] not in {"PUBLIC", "AUTHENTICATED", "PRIVATE"}
    ):
        raise EventValidationError("Article visibility payload shape is invalid")


ARTICLE_ADMIN_VIEWED = EventDefinition("article.admin_viewed.v1", _article_admin_viewed)
ARTICLE_VISIBILITY_CHANGED = EventDefinition(
    "article.visibility_changed.v1", _article_visibility_changed
)


def _aware_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _article_deleted(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"recipient_id", "administrative", "purge_after"}
        or not _recipient(payload["recipient_id"])
        or type(payload["administrative"]) is not bool
        or not _aware_datetime(payload["purge_after"])
    ):
        raise EventValidationError("Article deletion event payload shape is invalid")


def _article_restored(payload: Mapping[str, object]) -> None:
    if (
        set(payload) != {"recipient_id", "administrative"}
        or not _recipient(payload["recipient_id"])
        or type(payload["administrative"]) is not bool
    ):
        raise EventValidationError("Article restore event payload shape is invalid")


def _article_purge_requested(payload: Mapping[str, object]) -> None:
    if set(payload) != {"asset_count", "comment_count"} or any(
        isinstance(payload[field], bool)
        or not isinstance(payload[field], int)
        or payload[field] < 0
        for field in ("asset_count", "comment_count")
    ):
        raise EventValidationError("Article purge event payload shape is invalid")


ARTICLE_DELETED = EventDefinition("article.deleted.v1", _article_deleted)
ARTICLE_RESTORED = EventDefinition("article.restored.v1", _article_restored)
ARTICLE_PURGE_REQUESTED = EventDefinition(
    "article.purge_requested.v1",
    _article_purge_requested,
)


def _author_mask_changed(payload: Mapping[str, object]) -> None:
    if set(payload) != {"masked", "article_count", "cancelled_count"} or (
        type(payload["masked"]) is not bool
        or any(
            isinstance(payload[field], bool)
            or not isinstance(payload[field], int)
            or payload[field] < 0
            for field in ("article_count", "cancelled_count")
        )
    ):
        raise EventValidationError("Author mask event payload shape is invalid")


AUTHOR_MASK_CHANGED = EventDefinition(
    "article.author_mask_changed.v1",
    _author_mask_changed,
)
