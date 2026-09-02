from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.content.public import article_reader_target
from apps.core.ids import normalize_ulid

from ..models import Bookmark


class BookmarkCommandError(ValueError):
    code = "discovery.bookmark_invalid.v1"

    def __init__(self, message: str = "收藏操作无效。") -> None:
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BookmarkState:
    account_id: UUID
    article_id: str
    bookmarked: bool
    changed: bool


def _account_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise BookmarkCommandError from None


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise BookmarkCommandError from None


def set_bookmark(*, account_id, article_id: str, bookmarked: bool) -> BookmarkState:
    account = _account_id(account_id)
    article = _article_id(article_id)
    if type(bookmarked) is not bool:
        raise BookmarkCommandError
    if bookmarked:
        article_reader_target(actor_id=account, article_id=article)
        try:
            with transaction.atomic():
                _, changed = Bookmark.objects.get_or_create(
                    account_id=account,
                    article_id=article,
                )
        except IntegrityError:
            raise BookmarkCommandError("当前账户不能保存收藏。") from None
    else:
        with transaction.atomic():
            deleted, _ = Bookmark.objects.filter(
                account_id=account,
                article_id=article,
            ).delete()
        changed = deleted > 0
    return BookmarkState(account, article, bookmarked, changed)


def is_bookmarked(*, account_id, article_id: str) -> bool:
    return Bookmark.objects.filter(
        account_id=_account_id(account_id),
        article_id=_article_id(article_id),
    ).exists()
