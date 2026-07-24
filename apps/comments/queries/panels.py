from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q

from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..services.threads import sync_article_thread
from .threads import CommentSort, PublicCommentPage, public_comment_page


@dataclass(frozen=True, slots=True)
class BufferedCommentItem:
    id: str
    author_label: str
    body: str
    visible_at: datetime


@dataclass(frozen=True, slots=True)
class CommentThreadAccess:
    thread_id: str
    comments_enabled: bool
    can_view: bool
    can_post: bool
    post_login_required: bool
    can_manage_buffer: bool
    is_active_actor: bool
    actor_id: UUID | None
    owner_id: UUID
    is_owner: bool
    is_administrator: bool


@dataclass(frozen=True, slots=True)
class CommentPanel:
    thread_id: str
    comments_enabled: bool
    can_view: bool
    can_post: bool
    post_login_required: bool
    buffered_items: tuple[BufferedCommentItem, ...]
    public_page: PublicCommentPage


def article_comment_access(
    *,
    actor_id: UUID | None,
    article_id: str,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentThreadAccess:
    accounts = account_policy or default_comment_account_policy()
    thread, _ = sync_article_thread(actor_id=actor_id, article_id=article_id)
    active = actor_id is not None and accounts.is_active_account(actor_id)
    owner = active and actor_id == thread.owner_id
    administrator = active and accounts.is_administrator(actor_id)
    can_view = not thread.view_login_required or active
    can_post = thread.comments_enabled and (active or not thread.post_login_required)
    return CommentThreadAccess(
        thread_id=str(thread.id),
        comments_enabled=thread.comments_enabled,
        can_view=can_view,
        can_post=can_post,
        post_login_required=thread.post_login_required,
        can_manage_buffer=bool(owner or administrator),
        is_active_actor=active,
        actor_id=actor_id if active else None,
        owner_id=thread.owner_id,
        is_owner=bool(owner),
        is_administrator=bool(administrator),
    )


def article_comment_panel(
    *,
    actor_id: UUID | None,
    article_id: str,
    receipt_ids: tuple[str, ...] = (),
    account_policy: CommentAccountPolicy | None = None,
    sort: CommentSort | str = CommentSort.EARLIEST,
    cursor: str | None = None,
) -> CommentPanel:
    accounts = account_policy or default_comment_account_policy()
    access = article_comment_access(
        actor_id=actor_id,
        article_id=article_id,
        account_policy=accounts,
    )

    permitted = Q(pk__in=receipt_ids)
    if access.is_active_actor:
        permitted |= Q(author_id=actor_id)
    if access.can_manage_buffer:
        permitted = Q()
    rows = Comment.objects.filter(
        permitted,
        thread_id=access.thread_id,
        parent__isnull=True,
        state=Comment.State.BUFFERED,
    ).order_by("created_at", "id")[:20]
    return CommentPanel(
        thread_id=access.thread_id,
        comments_enabled=access.comments_enabled,
        can_view=access.can_view,
        can_post=access.can_post,
        post_login_required=access.post_login_required,
        buffered_items=tuple(
            BufferedCommentItem(
                id=row.id,
                author_label=(
                    "访客"
                    if row.author_kind == Comment.AuthorKind.ANONYMOUS
                    else "我"
                    if row.author_id == actor_id
                    else "登录用户"
                ),
                body=row.body,
                visible_at=row.visible_at,
            )
            for row in rows
        ),
        public_page=public_comment_page(
            thread_id=access.thread_id,
            can_view=access.can_view,
            sort=sort,
            cursor=cursor,
            account_policy=accounts,
            actor_id=access.actor_id,
            thread_owner_id=access.owner_id,
            is_administrator=access.is_administrator,
        ),
    )
