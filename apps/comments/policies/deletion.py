from enum import StrEnum
from uuid import UUID

from ..models import Comment


class CommentDeletionMode(StrEnum):
    SELF = "self"
    OWNER = "owner"
    ADMIN = "admin"


def comment_deletion_mode(
    *,
    state: str,
    author_kind: str,
    author_id: UUID | None,
    actor_id: UUID | None,
    thread_owner_id: UUID,
    is_administrator: bool,
) -> CommentDeletionMode | None:
    if state == Comment.State.DELETED or actor_id is None:
        return None
    if author_kind == Comment.AuthorKind.ACCOUNT and author_id == actor_id:
        return CommentDeletionMode.SELF
    if thread_owner_id == actor_id:
        return CommentDeletionMode.OWNER
    if is_administrator:
        return CommentDeletionMode.ADMIN
    return None
