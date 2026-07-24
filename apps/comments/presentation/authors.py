from uuid import UUID

from ..models import Comment
from ..ports import (
    CommentAccountPolicy,
    CommentAuthorPresentation,
    default_comment_account_policy,
)


def comment_author_presentation(
    *,
    author_kind: str,
    author_id: UUID | None,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentAuthorPresentation:
    if author_kind == Comment.AuthorKind.ANONYMOUS:
        return CommentAuthorPresentation("访客", None)
    if author_kind == Comment.AuthorKind.DELETED_ACCOUNT:
        return CommentAuthorPresentation("该账号已注销", None)
    if author_kind != Comment.AuthorKind.ACCOUNT or author_id is None:
        raise ValueError("Invalid comment author shape")
    accounts = account_policy or default_comment_account_policy()
    identity = accounts.public_identity(author_id)
    if identity is None:
        return CommentAuthorPresentation("账户用户", None)
    return CommentAuthorPresentation(identity.display_name, identity.profile_url)
