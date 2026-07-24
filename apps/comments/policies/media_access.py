from dataclasses import dataclass
from uuid import UUID

from apps.content.public import (
    ArticleLoginRequired,
    ArticleNotFound,
    article_comment_target,
)
from apps.core.ids import normalize_ulid

from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..targets import DiscussionTargetType


@dataclass(frozen=True, slots=True)
class CommentMediaAccessDecision:
    exists: bool
    can_bind: bool
    can_read: bool
    public_immutable: bool = False


def comment_media_access(
    *,
    actor_id: UUID | None,
    comment_id: str,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentMediaAccessDecision:
    try:
        identity = normalize_ulid(comment_id)
    except (TypeError, ValueError):
        return CommentMediaAccessDecision(False, False, False)
    comment = Comment.objects.select_related("thread").filter(pk=identity).first()
    if comment is None:
        return CommentMediaAccessDecision(False, False, False)
    accounts = account_policy or default_comment_account_policy()
    active = actor_id is not None and accounts.is_active_account(actor_id)
    owner = active and actor_id == comment.thread.owner_id
    author = active and actor_id == comment.author_id
    administrator = active and accounts.is_administrator(actor_id)
    delegated_anonymous_bind = (
        comment.author_kind == Comment.AuthorKind.ANONYMOUS and owner
    )
    can_bind = comment.state == Comment.State.BUFFERED and (
        author or delegated_anonymous_bind
    )
    privileged_read = owner or author or administrator

    target_readable = False
    if comment.thread.target_type == DiscussionTargetType.ARTICLE:
        try:
            article_comment_target(
                actor_id=actor_id,
                article_id=comment.thread.target_id,
            )
        except (ArticleLoginRequired, ArticleNotFound):
            target_readable = False
        else:
            target_readable = True
    elif comment.thread.target_type == DiscussionTargetType.GUESTBOOK:
        target_readable = not comment.thread.view_login_required or active

    can_read = privileged_read or (
        comment.state == Comment.State.VISIBLE
        and target_readable
        and (not comment.thread.view_login_required or active)
    )
    return CommentMediaAccessDecision(True, can_bind, can_read)
