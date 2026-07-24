from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from django.db import transaction

from apps.core.ids import normalize_ulid

from ..models import Comment


class CommentPublicationOutcome(StrEnum):
    PUBLISHED = "published"
    ALREADY_VISIBLE = "already_visible"
    NOT_DUE = "not_due"
    DELETED = "deleted"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class CommentPublicationResult:
    comment_id: str
    outcome: CommentPublicationOutcome


def _aware_now(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("now must be timezone-aware")
    return value


def _batch_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    return value


def due_buffered_comment_ids(
    *, now: datetime, batch_size: int = 100
) -> tuple[str, ...]:
    cutoff = _aware_now(now)
    limit = _batch_size(batch_size)
    with transaction.atomic():
        return tuple(
            Comment.objects.select_for_update(skip_locked=True)
            .filter(
                state=Comment.State.BUFFERED,
                visible_at__lte=cutoff,
            )
            .order_by("visible_at", "id")
            .values_list("id", flat=True)[:limit]
        )


def publish_due_comment(*, comment_id: str, now: datetime) -> CommentPublicationResult:
    identity = normalize_ulid(comment_id)
    cutoff = _aware_now(now)
    with transaction.atomic():
        comment = Comment.objects.select_for_update().filter(pk=identity).first()
        if comment is None:
            return CommentPublicationResult(identity, CommentPublicationOutcome.MISSING)
        if comment.state == Comment.State.DELETED:
            return CommentPublicationResult(identity, CommentPublicationOutcome.DELETED)
        if comment.state == Comment.State.VISIBLE:
            return CommentPublicationResult(
                identity,
                CommentPublicationOutcome.ALREADY_VISIBLE,
            )
        if comment.visible_at > cutoff:
            return CommentPublicationResult(identity, CommentPublicationOutcome.NOT_DUE)
        updated = Comment.objects.filter(
            pk=identity,
            state=Comment.State.BUFFERED,
            visible_at__lte=cutoff,
        ).update(state=Comment.State.VISIBLE, updated_at=cutoff)
        outcome = (
            CommentPublicationOutcome.PUBLISHED
            if updated == 1
            else CommentPublicationOutcome.ALREADY_VISIBLE
        )
        return CommentPublicationResult(identity, outcome)
