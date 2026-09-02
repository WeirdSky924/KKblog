from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, ProgrammingError, transaction

from apps.content.public import article_reader_target
from apps.core.ids import normalize_ulid

from ..models import ArticleLike


class ArticleLikeCommandError(ValueError):
    code = "discovery.article_like_invalid.v1"

    def __init__(self, message: str = "点赞操作无效。") -> None:
        self.safe_message = message
        super().__init__(message)


class ArticleLikeUnavailableError(RuntimeError):
    code = "discovery.article_like_unavailable.v1"

    def __init__(self) -> None:
        self.safe_message = "点赞功能正在升级，请稍后再试。"
        super().__init__(self.safe_message)


@dataclass(frozen=True, slots=True)
class ArticleLikeState:
    account_id: UUID
    article_id: str
    liked: bool
    changed: bool


def _account_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleLikeCommandError from None


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleLikeCommandError from None


def _is_missing_table(error: ProgrammingError) -> bool:
    return getattr(error.__cause__, "sqlstate", None) == "42P01"


def set_article_like(*, account_id, article_id: str, liked: bool) -> ArticleLikeState:
    account = _account_id(account_id)
    article = _article_id(article_id)
    if type(liked) is not bool:
        raise ArticleLikeCommandError
    if liked:
        article_reader_target(actor_id=account, article_id=article)
    try:
        with transaction.atomic():
            if liked:
                _, changed = ArticleLike.objects.get_or_create(
                    account_id=account,
                    article_id=article,
                )
            else:
                deleted, _ = ArticleLike.objects.filter(
                    account_id=account,
                    article_id=article,
                ).delete()
                changed = deleted > 0
    except ProgrammingError as exc:
        if _is_missing_table(exc):
            raise ArticleLikeUnavailableError from None
        raise
    except IntegrityError:
        raise ArticleLikeCommandError("当前账户不能保存点赞。") from None
    return ArticleLikeState(account, article, liked, changed)


def is_article_liked(*, account_id, article_id: str) -> bool:
    try:
        return ArticleLike.objects.filter(
            account_id=_account_id(account_id),
            article_id=_article_id(article_id),
        ).exists()
    except ProgrammingError as exc:
        if _is_missing_table(exc):
            return False
        raise
