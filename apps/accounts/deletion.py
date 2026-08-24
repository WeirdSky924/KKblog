from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from apps.core.ids import is_ulid, normalize_ulid

AccountDeletionCleanup = Callable[[UUID], object]
_account_deletion_cleanup: AccountDeletionCleanup | None = None


def configure_account_deletion_cleanup(provider: AccountDeletionCleanup) -> None:
    if not callable(provider):
        raise TypeError("account deletion cleanup provider must be callable")
    global _account_deletion_cleanup
    _account_deletion_cleanup = provider


def run_account_deletion_cleanup(account_id: UUID) -> object | None:
    if not isinstance(account_id, UUID):
        raise ValueError("Invalid account deletion cleanup ID")
    if _account_deletion_cleanup is None:
        return None
    return _account_deletion_cleanup(account_id)


class AuthorArticleDecision(StrEnum):
    NO_ARTICLES = "no_articles"
    DELETE_ALL = "delete_all"
    EXPORT_THEN_DELETE = "export_then_delete"


@dataclass(frozen=True, slots=True)
class AccountDeletionDisposition:
    """A content-owned, stable decision prepared before deleting an author."""

    disposition_id: str
    account_id: UUID
    decision: AuthorArticleDecision
    article_count: int

    def __post_init__(self) -> None:
        try:
            account_id = UUID(str(self.account_id))
            decision = AuthorArticleDecision(self.decision)
        except (TypeError, ValueError):
            raise ValueError("Invalid author article disposition") from None
        if not is_ulid(self.disposition_id):
            raise ValueError("Invalid author article disposition")
        if (
            isinstance(self.article_count, bool)
            or not isinstance(self.article_count, int)
            or self.article_count < 0
            or self.article_count > 1_000_000
            or (
                decision == AuthorArticleDecision.NO_ARTICLES
                and self.article_count != 0
            )
            or (
                decision
                in {
                    AuthorArticleDecision.DELETE_ALL,
                    AuthorArticleDecision.EXPORT_THEN_DELETE,
                }
                and self.article_count == 0
            )
        ):
            raise ValueError("Invalid author article disposition")
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "disposition_id", normalize_ulid(self.disposition_id))


__all__ = [
    "AccountDeletionDisposition",
    "AccountDeletionCleanup",
    "AuthorArticleDecision",
    "configure_account_deletion_cleanup",
    "run_account_deletion_cleanup",
]
