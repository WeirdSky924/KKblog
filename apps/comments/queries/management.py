from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Count, Max, Q

from apps.core.pagination import PageSlice

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
    buffered_page: PageSlice[OwnerBufferedComment] | None = None
    article_page: PageSlice[OwnerCommentArticle] | None = None


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
    *,
    actor_id,
    buffered_limit: int = 50,
    article_limit: int = 100,
    buffered_page: int | None = None,
    article_page: int | None = None,
    page_size: int = 20,
) -> OwnerCommentWorkspace:
    actor = _actor_id(actor_id)
    if (
        isinstance(buffered_limit, bool)
        or buffered_limit not in {20, 50}
        or isinstance(article_limit, bool)
        or article_limit not in {20, 50, 100}
    ):
        raise ValueError("comment workspace limits are invalid")
    if (buffered_page is not None or article_page is not None) and (
        isinstance(page_size, bool) or page_size not in (10, 20, 50)
    ):
        raise ValueError("comment workspace page size is invalid")
    if buffered_page is not None and (
        isinstance(buffered_page, bool) or buffered_page < 1
    ):
        raise ValueError("buffered comment page is invalid")
    if article_page is not None and (
        isinstance(article_page, bool) or article_page < 1
    ):
        raise ValueError("comment article page is invalid")
    threads = DiscussionThread.objects.filter(
        owner_id=actor,
        target_type=DiscussionTargetType.ARTICLE,
    )
    buffered_ordered = (
        Comment.objects.select_related("thread")
        .filter(thread__in=threads, state=Comment.State.BUFFERED)
        .order_by("visible_at", "id")
    )
    if buffered_page is None:
        buffered = tuple(buffered_ordered[:buffered_limit])
        buffered_slice = None
    else:
        paginator = Paginator(buffered_ordered, page_size)
        selected = paginator.get_page(buffered_page)
        buffered = tuple(selected.object_list)
        buffered_slice = PageSlice(
            items=tuple(
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
            page_number=selected.number,
            page_size=page_size,
            total_items=paginator.count,
            total_pages=paginator.num_pages,
            has_previous=selected.has_previous(),
            has_next=selected.has_next(),
        )
    groups_ordered = threads.annotate(
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
    ).order_by("-latest_at", "target_id")
    if article_page is None:
        groups = tuple(groups_ordered[:article_limit])
        article_slice = None
    else:
        paginator = Paginator(groups_ordered, page_size)
        selected = paginator.get_page(article_page)
        groups = tuple(selected.object_list)
        article_slice = PageSlice(
            items=tuple(
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
        else tuple(
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
        )
    )
    article_items = (
        article_slice.items
        if article_slice is not None
        else tuple(
            OwnerCommentArticle(
                article_id=row.target_id,
                comments_enabled=row.comments_enabled,
                buffered_count=row.buffered_count,
                visible_count=row.visible_count,
                deleted_count=row.deleted_count,
                latest_at=row.latest_at,
            )
            for row in groups
        )
    )
    return OwnerCommentWorkspace(
        buffered_items=buffered_items,
        articles=article_items,
        buffered_page=buffered_slice,
        article_page=article_slice,
    )
