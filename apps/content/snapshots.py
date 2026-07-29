from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.conf import settings

from .models import ArticleRevision

MIN_BODY_BYTES = 64 * 1024
MAX_BODY_BYTES = 2 * 1024 * 1024
DEFAULT_BODY_BYTES = MAX_BODY_BYTES

ArticleBodyLimitProvider = Callable[[], int]


def _settings_article_body_limit() -> int:
    return getattr(settings, "ARTICLE_BODY_MAX_BYTES", DEFAULT_BODY_BYTES)


_article_body_limit_provider: ArticleBodyLimitProvider = _settings_article_body_limit

ContentFormat = ArticleRevision.ContentFormat
SummaryMode = ArticleRevision.SummaryMode
Visibility = ArticleRevision.Visibility


@dataclass(frozen=True, slots=True)
class ArticleBodyLimit:
    maximum_bytes: int = DEFAULT_BODY_BYTES

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_bytes, bool)
            or not isinstance(self.maximum_bytes, int)
            or not MIN_BODY_BYTES <= self.maximum_bytes <= MAX_BODY_BYTES
        ):
            raise ValueError("Article body limit must be between 64 KiB and 2 MiB")

    @classmethod
    def configured(cls) -> ArticleBodyLimit:
        return cls(_article_body_limit_provider())


def configure_article_body_limit_provider(provider: ArticleBodyLimitProvider) -> None:
    if not callable(provider):
        raise TypeError("article body limit provider must be callable")
    global _article_body_limit_provider
    _article_body_limit_provider = provider


@dataclass(frozen=True, slots=True)
class ArticleSnapshot:
    content_format: ContentFormat | str
    title: str
    body: str | dict[str, Any]
    summary_mode: SummaryMode | str = SummaryMode.AUTO
    custom_summary: str | None = None
    visibility: Visibility | str = Visibility.PUBLIC
    section_id: UUID | str | None = None
    tag_ids: tuple[UUID | str, ...] = ()
    cover_asset_id: str | None = None
    body_asset_ids: tuple[str, ...] = ()
    comments_enabled: bool = True
    comments_view_login: bool = False
    comments_post_login: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.body_asset_ids, tuple):
            object.__setattr__(self, "body_asset_ids", tuple(self.body_asset_ids))
        if not isinstance(self.tag_ids, tuple):
            object.__setattr__(self, "tag_ids", tuple(self.tag_ids))


@dataclass(frozen=True, slots=True)
class ArticleWriteResult:
    article_id: str
    revision_id: str
    row_version: int
