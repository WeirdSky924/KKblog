from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q

from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..services.threads import sync_article_thread


@dataclass(frozen=True, slots=True)
class BufferedCommentItem:
    id: str
    author_label: str
    body: str
    visible_at: datetime


@dataclass(frozen=True, slots=True)
class CommentPanel:
    thread_id: str
    comments_enabled: bool
    can_view: bool
    can_post: bool
    post_login_required: bool
    buffered_items: tuple[BufferedCommentItem, ...]


def article_comment_panel(
    *,
    actor_id: UUID | None,
    article_id: str,
    receipt_ids: tuple[str, ...] = (),
    account_policy: CommentAccountPolicy | None = None,
) -> CommentPanel:
    accounts = account_policy or default_comment_account_policy()
    thread, _ = sync_article_thread(actor_id=actor_id, article_id=article_id)
    active = actor_id is not None and accounts.is_active_account(actor_id)
    owner = active and actor_id == thread.owner_id
    administrator = active and accounts.is_administrator(actor_id)
    can_view = not thread.view_login_required or active
    can_post = thread.comments_enabled and (active or not thread.post_login_required)

    permitted = Q(pk__in=receipt_ids)
    if active:
        permitted |= Q(author_id=actor_id)
    if owner or administrator:
        permitted = Q()
    rows = Comment.objects.filter(
        permitted,
        thread=thread,
        parent__isnull=True,
        state=Comment.State.BUFFERED,
    ).order_by("created_at", "id")[:20]
    return CommentPanel(
        thread_id=str(thread.id),
        comments_enabled=thread.comments_enabled,
        can_view=can_view,
        can_post=can_post,
        post_login_required=thread.post_login_required,
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
    )
