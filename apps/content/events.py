from collections.abc import Mapping
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
