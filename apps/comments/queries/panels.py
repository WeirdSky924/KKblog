from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q

from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..services.threads import sync_article_thread, sync_guestbook_thread
from ..targets import DiscussionTargetType
from .threads import CommentSort, PublicCommentPage, public_comment_page


@dataclass(frozen=True, slots=True)
class BufferedCommentItem:
    id: str
    author_label: str
    body: str
    visible_at: datetime
    is_reply: bool


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


def _thread_access(
    *,
    actor_id: UUID | None,
    thread,
    account_policy: CommentAccountPolicy,
) -> CommentThreadAccess:
    active = actor_id is not None and account_policy.is_active_account(actor_id)
    owner = active and actor_id == thread.owner_id
    administrator = active and account_policy.is_administrator(actor_id)
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


def comment_thread_access(
    *,
    actor_id: UUID | None,
    target_type: DiscussionTargetType | str,
    target_id: str,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentThreadAccess:
    accounts = account_policy or default_comment_account_policy()
    target = DiscussionTargetType(target_type)
    thread = (
        sync_article_thread(actor_id=actor_id, article_id=target_id)[0]
        if target is DiscussionTargetType.ARTICLE
        else sync_guestbook_thread(account_policy=accounts)
    )
    return _thread_access(
        actor_id=actor_id,
        thread=thread,
        account_policy=accounts,
    )


def article_comment_access(
    *,
    actor_id: UUID | None,
    article_id: str,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentThreadAccess:
    return comment_thread_access(
        actor_id=actor_id,
        target_type=DiscussionTargetType.ARTICLE,
        target_id=article_id,
        account_policy=account_policy,
    )


def guestbook_comment_access(
    *,
    actor_id: UUID | None,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentThreadAccess:
    return comment_thread_access(
        actor_id=actor_id,
        target_type=DiscussionTargetType.GUESTBOOK,
        target_id="site",
        account_policy=account_policy,
    )


def comment_thread_panel(
    *,
    actor_id: UUID | None,
    target_type: DiscussionTargetType | str,
    target_id: str,
    receipt_ids: tuple[str, ...] = (),
    account_policy: CommentAccountPolicy | None = None,
    sort: CommentSort | str = CommentSort.EARLIEST,
    cursor: str | None = None,
) -> CommentPanel:
    accounts = account_policy or default_comment_account_policy()
    target = DiscussionTargetType(target_type)
    access = comment_thread_access(
        actor_id=actor_id,
        target_type=target,
        target_id=target_id,
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
                is_reply=row.parent_id is not None,
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
            can_reply=access.is_active_actor and access.comments_enabled,
            can_report=access.is_active_actor,
            can_pin=(
                target is DiscussionTargetType.ARTICLE and access.can_manage_buffer
            ),
        ),
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
    return comment_thread_panel(
        actor_id=actor_id,
        target_type=DiscussionTargetType.ARTICLE,
        target_id=article_id,
        receipt_ids=receipt_ids,
        account_policy=account_policy,
        sort=sort,
        cursor=cursor,
    )


def guestbook_comment_panel(
    *,
    actor_id: UUID | None,
    receipt_ids: tuple[str, ...] = (),
    account_policy: CommentAccountPolicy | None = None,
    sort: CommentSort | str = CommentSort.EARLIEST,
    cursor: str | None = None,
) -> CommentPanel:
    return comment_thread_panel(
        actor_id=actor_id,
        target_type=DiscussionTargetType.GUESTBOOK,
        target_id="site",
        receipt_ids=receipt_ids,
        account_policy=account_policy,
        sort=sort,
        cursor=cursor,
    )
