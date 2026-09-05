from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Count, Max, Q

from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY
from apps.core.ids import normalize_ulid
from apps.core.pagination import PageSlice

from ..models import Comment, DiscussionThread
from ..ports import CommentAccountPolicy, default_comment_account_policy
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
    buffered_page: PageSlice[AdminCommentItem] | None = None
    thread_page: PageSlice[AdminCommentThreadItem] | None = None


def _require_administrator(
    actor_id,
    *,
    account_policy: CommentAccountPolicy,
) -> None:
    if not account_policy.is_active_account(
        actor_id
    ) or not account_policy.is_administrator(actor_id):
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
    *,
    actor_id,
    buffered_limit: int = 100,
    thread_limit: int = 200,
    buffered_page: int | None = None,
    thread_page: int | None = None,
    page_size: int = 20,
    include_buffered: bool = True,
    include_threads: bool = True,
    account_policy: CommentAccountPolicy | None = None,
) -> AdminCommentWorkspace:
    accounts = account_policy or default_comment_account_policy()
    _require_administrator(actor_id, account_policy=accounts)
    if (
        isinstance(buffered_limit, bool)
        or not 1 <= buffered_limit <= 200
        or isinstance(thread_limit, bool)
        or not 1 <= thread_limit <= 500
    ):
        raise ValueError("Invalid administrator comment query limit")
    if (buffered_page is not None or thread_page is not None) and (
        isinstance(page_size, bool) or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid administrator comment page size")
    if buffered_page is not None and (
        isinstance(buffered_page, bool) or buffered_page < 1
    ):
        raise ValueError("Invalid buffered comment page")
    if thread_page is not None and (isinstance(thread_page, bool) or thread_page < 1):
        raise ValueError("Invalid comment thread page")
    if type(include_buffered) is not bool or type(include_threads) is not bool:
        raise ValueError("Invalid administrator comment collection flags")
    buffered_ordered = (
        Comment.objects.select_related("thread")
        .filter(state=Comment.State.BUFFERED)
        .order_by("visible_at", "id")
    )
    if not include_buffered:
        buffered = ()
        buffered_slice = None
    elif buffered_page is None:
        buffered = tuple(buffered_ordered[:buffered_limit])
        buffered_slice = None
    else:
        paginator = Paginator(buffered_ordered, page_size)
        selected = paginator.get_page(buffered_page)
        buffered = tuple(selected.object_list)
        buffered_slice = PageSlice(
            items=tuple(_item(comment) for comment in buffered),
            page_number=selected.number,
            page_size=page_size,
            total_items=paginator.count,
            total_pages=paginator.num_pages,
            has_previous=selected.has_previous(),
            has_next=selected.has_next(),
        )
    threads_ordered = DiscussionThread.objects.annotate(
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
    ).order_by("-latest_at", "target_type", "target_id")
    if not include_threads:
        threads = ()
        thread_slice = None
    elif thread_page is None:
        threads = tuple(threads_ordered[:thread_limit])
        thread_slice = None
    else:
        paginator = Paginator(threads_ordered, page_size)
        selected = paginator.get_page(thread_page)
        threads = tuple(selected.object_list)
        thread_slice = PageSlice(
            items=tuple(
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
            page_number=selected.number,
            page_size=page_size,
            total_items=paginator.count,
            total_pages=paginator.num_pages,
            has_previous=selected.has_previous(),
            has_next=selected.has_next(),
        )
    buffered_items = (
        buffered_slice.items
        if buffered_slice is not None
        else tuple(_item(comment) for comment in buffered)
    )
    thread_items = (
        thread_slice.items
        if thread_slice is not None
        else tuple(
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
        )
    )
    return AdminCommentWorkspace(
        buffered_items=buffered_items,
        threads=thread_items,
        buffered_page=buffered_slice,
        thread_page=thread_slice,
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
    *,
    actor_id,
    target_type: str,
    target_id: str,
    limit: int = 300,
    page: int | None = None,
    page_size: int = 20,
    account_policy: CommentAccountPolicy | None = None,
) -> tuple[AdminCommentItem, ...] | PageSlice[AdminCommentItem]:
    accounts = account_policy or default_comment_account_policy()
    _require_administrator(actor_id, account_policy=accounts)
    normalized_type, normalized_id = _target(target_type, target_id)
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator comment query limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid administrator comment page")
    thread = DiscussionThread.objects.filter(
        target_type=normalized_type,
        target_id=normalized_id,
    ).first()
    if thread is None:
        raise AdminCommentNotFound
    comments = (
        Comment.objects.select_related("thread")
        .filter(thread=thread)
        .order_by("created_at", "id")
    )
    if page is None:
        return tuple(_item(comment) for comment in comments[:limit])
    paginator = Paginator(comments, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(_item(comment) for comment in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def admin_comment_detail(
    *,
    actor_id,
    comment_id: str,
    account_policy: CommentAccountPolicy | None = None,
) -> AdminCommentDetail:
    accounts = account_policy or default_comment_account_policy()
    _require_administrator(actor_id, account_policy=accounts)
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
