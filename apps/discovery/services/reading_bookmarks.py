from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from django.db import IntegrityError, ProgrammingError, transaction

from apps.content.public import article_reader_target
from apps.core.ids import normalize_ulid

from ..models import ReadingBookmark

PROGRESS_PRECISION = Decimal("0.000001")


class ReadingBookmarkCommandError(ValueError):
    code = "discovery.reading_bookmark_invalid.v1"

    def __init__(self, message: str = "阅读位置无效。") -> None:
        self.safe_message = message
        super().__init__(message)


class ReadingBookmarkUnavailableError(RuntimeError):
    code = "discovery.reading_bookmark_unavailable.v1"

    def __init__(self) -> None:
        self.safe_message = "阅读书签正在升级，请稍后再试。"
        super().__init__(self.safe_message)


@dataclass(frozen=True, slots=True)
class ReadingBookmarkState:
    account_id: UUID
    article_id: str
    revision_id: str
    progress: Decimal
    created: bool


def _account_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ReadingBookmarkCommandError from None


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ReadingBookmarkCommandError from None


def _progress(value) -> Decimal:
    if isinstance(value, bool):
        raise ReadingBookmarkCommandError
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ReadingBookmarkCommandError from None
    if not normalized.is_finite() or normalized < 0 or normalized > 1:
        raise ReadingBookmarkCommandError
    return normalized.quantize(PROGRESS_PRECISION, rounding=ROUND_HALF_UP)


def _is_missing_reading_bookmark_table(error: ProgrammingError) -> bool:
    return getattr(error.__cause__, "sqlstate", None) == "42P01"


def save_reading_bookmark(
    *, account_id, article_id: str, progress
) -> ReadingBookmarkState:
    account = _account_id(account_id)
    article = _article_id(article_id)
    normalized_progress = _progress(progress)
    readable = article_reader_target(actor_id=account, article_id=article)
    try:
        with transaction.atomic():
            _, created = ReadingBookmark.objects.update_or_create(
                account_id=account,
                article_id=article,
                defaults={
                    "revision_id": readable.revision_id,
                    "progress": normalized_progress,
                },
            )
    except ProgrammingError as exc:
        if _is_missing_reading_bookmark_table(exc):
            raise ReadingBookmarkUnavailableError from None
        raise
    except IntegrityError:
        raise ReadingBookmarkCommandError("当前账户不能保存阅读书签。") from None
    return ReadingBookmarkState(
        account_id=account,
        article_id=article,
        revision_id=readable.revision_id,
        progress=normalized_progress,
        created=created,
    )


def reading_bookmark_progress(*, account_id, article_id: str) -> Decimal | None:
    try:
        return (
            ReadingBookmark.objects.filter(
                account_id=_account_id(account_id),
                article_id=_article_id(article_id),
            )
            .values_list("progress", flat=True)
            .first()
        )
    except ProgrammingError as exc:
        if _is_missing_reading_bookmark_table(exc):
            return None
        raise
