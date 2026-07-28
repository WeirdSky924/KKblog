from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Count, Max, Q

from ..models import Comment, DiscussionThread
from ..targets import DiscussionTargetType


class OwnerCommentWorkspaceError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class OwnerBufferedComment:
    comment_id: str
    article_id: str
    author_label: str
    body: str
    created_at: datetime
    visible_at: datetime
    is_reply: bool


@dataclass(frozen=True, slots=True)
class OwnerCommentArticle:
    article_id: str
    comments_enabled: bool
    buffered_count: int
    visible_count: int
    deleted_count: int
    latest_at: datetime | None

    @property
    def total_count(self) -> int:
        return self.buffered_count + self.visible_count + self.deleted_count


@dataclass(frozen=True, slots=True)
class OwnerCommentWorkspace:
    buffered_items: tuple[OwnerBufferedComment, ...]
    articles: tuple[OwnerCommentArticle, ...]


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise OwnerCommentWorkspaceError from None


def _author_label(comment: Comment, actor_id: UUID) -> str:
    if comment.author_kind == Comment.AuthorKind.ANONYMOUS:
        return "访客"
    if comment.author_kind == Comment.AuthorKind.DELETED_ACCOUNT:
        return "该账号已注销"
    return "我" if comment.author_id == actor_id else "登录用户"


def owner_comment_workspace(
    *, actor_id, buffered_limit: int = 50, article_limit: int = 100
) -> OwnerCommentWorkspace:
    actor = _actor_id(actor_id)
    if (
        isinstance(buffered_limit, bool)
        or buffered_limit not in {20, 50}
        or isinstance(article_limit, bool)
        or article_limit not in {20, 50, 100}
    ):
        raise ValueError("comment workspace limits are invalid")
    threads = DiscussionThread.objects.filter(
        owner_id=actor,
        target_type=DiscussionTargetType.ARTICLE,
    )
    buffered = (
        Comment.objects.select_related("thread")
        .filter(thread__in=threads, state=Comment.State.BUFFERED)
        .order_by("visible_at", "id")[:buffered_limit]
    )
    groups = threads.annotate(
        buffered_count=Count(
            "comments", filter=Q(comments__state=Comment.State.BUFFERED)
        ),
        visible_count=Count(
            "comments", filter=Q(comments__state=Comment.State.VISIBLE)
        ),
        deleted_count=Count(
            "comments", filter=Q(comments__state=Comment.State.DELETED)
        ),
        latest_at=Max("comments__created_at"),
    ).order_by("-latest_at", "target_id")[:article_limit]
    return OwnerCommentWorkspace(
        buffered_items=tuple(
            OwnerBufferedComment(
                comment_id=row.id,
                article_id=row.thread.target_id,
                author_label=_author_label(row, actor),
                body=row.body,
                created_at=row.created_at,
                visible_at=row.visible_at,
                is_reply=row.parent_id is not None,
            )
            for row in buffered
        ),
        articles=tuple(
            OwnerCommentArticle(
                article_id=row.target_id,
                comments_enabled=row.comments_enabled,
                buffered_count=row.buffered_count,
                visible_count=row.visible_count,
                deleted_count=row.deleted_count,
                latest_at=row.latest_at,
            )
            for row in groups
        ),
    )
