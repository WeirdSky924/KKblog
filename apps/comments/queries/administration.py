from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Count, Max, Q

from apps.accounts.public import is_administrator
from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY
from apps.core.ids import normalize_ulid

from ..models import Comment, DiscussionThread
from ..targets import GUESTBOOK_TARGET_ID, DiscussionTargetType


class AdminCommentNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class AdminCommentItem:
    id: str
    target_type: str
    target_id: str
    author_id: UUID | None
    author_kind: str
    body: str
    state: str
    depth: int
    is_reply: bool
    masked_ip: str
    reason_provided: bool
    visible_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminCommentDetail(AdminCommentItem):
    client_ip: str
    deletion_reason: str
    parent_id: str | None
    root_id: str
    reply_count: int


@dataclass(frozen=True, slots=True)
class AdminCommentThreadItem:
    target_type: str
    target_id: str
    owner_id: UUID
    comments_enabled: bool
    buffered_count: int
    visible_count: int
    deleted_count: int
    latest_at: datetime | None

    @property
    def total_count(self) -> int:
        return self.buffered_count + self.visible_count + self.deleted_count


@dataclass(frozen=True, slots=True)
class AdminCommentWorkspace:
    buffered_items: tuple[AdminCommentItem, ...]
    threads: tuple[AdminCommentThreadItem, ...]


def _require_administrator(actor_id) -> None:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator comment access denied")


def _item(comment: Comment) -> AdminCommentItem:
    return AdminCommentItem(
        id=comment.id,
        target_type=comment.thread.target_type,
        target_id=comment.thread.target_id,
        author_id=comment.author_id,
        author_kind=comment.author_kind,
        body=comment.body,
        state=comment.state,
        depth=comment.depth,
        is_reply=comment.parent_id is not None,
        masked_ip=DEFAULT_REDACTION_POLICY.mask_ip(comment.client_ip),
        reason_provided=bool(comment.deletion_reason),
        visible_at=comment.visible_at,
        created_at=comment.created_at,
    )


def admin_comment_workspace(
    *, actor_id, buffered_limit: int = 100, thread_limit: int = 200
) -> AdminCommentWorkspace:
    _require_administrator(actor_id)
    if (
        isinstance(buffered_limit, bool)
        or not 1 <= buffered_limit <= 200
        or isinstance(thread_limit, bool)
        or not 1 <= thread_limit <= 500
    ):
        raise ValueError("Invalid administrator comment query limit")
    buffered = (
        Comment.objects.select_related("thread")
        .filter(state=Comment.State.BUFFERED)
        .order_by("visible_at", "id")[:buffered_limit]
    )
    threads = DiscussionThread.objects.annotate(
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
    ).order_by("-latest_at", "target_type", "target_id")[:thread_limit]
    return AdminCommentWorkspace(
        buffered_items=tuple(_item(comment) for comment in buffered),
        threads=tuple(
            AdminCommentThreadItem(
                target_type=row.target_type,
                target_id=row.target_id,
                owner_id=row.owner_id,
                comments_enabled=row.comments_enabled,
                buffered_count=row.buffered_count,
                visible_count=row.visible_count,
                deleted_count=row.deleted_count,
                latest_at=row.latest_at,
            )
            for row in threads
        ),
    )


def _target(target_type: str, target_id: str) -> tuple[str, str]:
    try:
        normalized_type = DiscussionTargetType(target_type)
    except (TypeError, ValueError):
        raise AdminCommentNotFound from None
    if normalized_type == DiscussionTargetType.ARTICLE:
        try:
            normalized_id = normalize_ulid(target_id)
        except (TypeError, ValueError):
            raise AdminCommentNotFound from None
    elif target_id == GUESTBOOK_TARGET_ID:
        normalized_id = GUESTBOOK_TARGET_ID
    else:
        raise AdminCommentNotFound
    return normalized_type.value, normalized_id


def admin_comments_for_target(
    *, actor_id, target_type: str, target_id: str, limit: int = 300
) -> tuple[AdminCommentItem, ...]:
    _require_administrator(actor_id)
    normalized_type, normalized_id = _target(target_type, target_id)
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator comment query limit")
    thread = DiscussionThread.objects.filter(
        target_type=normalized_type,
        target_id=normalized_id,
    ).first()
    if thread is None:
        raise AdminCommentNotFound
    comments = (
        Comment.objects.select_related("thread")
        .filter(thread=thread)
        .order_by("created_at", "id")[:limit]
    )
    return tuple(_item(comment) for comment in comments)


def admin_comment_detail(*, actor_id, comment_id: str) -> AdminCommentDetail:
    _require_administrator(actor_id)
    try:
        identity = normalize_ulid(comment_id)
    except (TypeError, ValueError):
        raise AdminCommentNotFound from None
    comment = Comment.objects.select_related("thread").filter(pk=identity).first()
    if comment is None:
        raise AdminCommentNotFound
    item = _item(comment)
    return AdminCommentDetail(
        **{
            field: getattr(item, field)
            for field in AdminCommentItem.__dataclass_fields__
        },
        client_ip=comment.client_ip,
        deletion_reason=comment.deletion_reason or "",
        parent_id=comment.parent_id,
        root_id=comment.root_id,
        reply_count=comment.reply_count,
    )


__all__ = [
    "AdminCommentDetail",
    "AdminCommentItem",
    "AdminCommentNotFound",
    "AdminCommentThreadItem",
    "AdminCommentWorkspace",
    "admin_comment_detail",
    "admin_comment_workspace",
    "admin_comments_for_target",
]
