from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from apps.content.public import (
    ArticleLoginRequired,
    ArticleNotFound,
    article_comment_target,
)
from apps.core.ids import normalize_ulid

from ..models import Comment
from ..targets import DiscussionTargetType


class CommentReportTargetError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ReportableCommentTarget:
    comment_id: str
    author_id: UUID | None
    target_type: DiscussionTargetType
    target_id: str


def reportable_comment_target(
    *,
    comment_id: str,
    actor_id: UUID,
    now: datetime | None = None,
) -> ReportableCommentTarget:
    try:
        identity = normalize_ulid(comment_id)
    except (TypeError, ValueError):
        raise CommentReportTargetError("Comment is not reportable") from None
    cutoff = now or timezone.now()
    row = (
        Comment.objects.select_related("thread")
        .filter(
            pk=identity,
            state=Comment.State.VISIBLE,
            visible_at__lte=cutoff,
        )
        .first()
    )
    if row is None:
        raise CommentReportTargetError("Comment is not reportable")
    target_type = DiscussionTargetType(row.thread.target_type)
    if target_type is DiscussionTargetType.ARTICLE:
        try:
            article_comment_target(
                actor_id=actor_id,
                article_id=row.thread.target_id,
            )
        except (ArticleLoginRequired, ArticleNotFound):
            raise CommentReportTargetError("Comment is not reportable") from None
    elif row.thread.view_login_required and actor_id is None:
        raise CommentReportTargetError("Comment is not reportable")
    return ReportableCommentTarget(
        comment_id=row.id,
        author_id=row.author_id,
        target_type=target_type,
        target_id=row.thread.target_id,
    )
