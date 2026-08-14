from dataclasses import dataclass
from datetime import datetime

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from apps.accounts.public import is_administrator
from apps.core.ids import normalize_ulid

from ..models import Article, ArticlePublication


@dataclass(frozen=True, slots=True)
class AdminPublishedRevision:
    revision_id: str
    sequence: int
    title: str
    published_at: datetime
    content_format: str
    visibility: str
    is_current: bool


def publication_history_schema_ready() -> bool:
    return (
        MigrationRecorder(connection)
        .migration_qs.filter(
            app="content",
            name="0016_article_publication_history",
        )
        .exists()
    )


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise LookupError("Administrator article history not found") from None


def _fallback_history(article: Article) -> tuple[AdminPublishedRevision, ...]:
    revision = article.published_revision
    if revision is None:
        return ()
    published_at = (
        article.last_published_at or article.published_at or revision.created_at
    )
    return (
        AdminPublishedRevision(
            revision_id=revision.id,
            sequence=revision.sequence,
            title=revision.title,
            published_at=published_at,
            content_format=revision.content_format,
            visibility=revision.visibility,
            is_current=True,
        ),
    )


def admin_published_revision_history(
    *, actor_id, article_id: str
) -> tuple[AdminPublishedRevision, ...]:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator publication history access denied")
    identity = _article_id(article_id)
    try:
        article = Article.objects.select_related("published_revision").get(pk=identity)
    except Article.DoesNotExist:
        raise LookupError("Administrator article history not found") from None
    if not publication_history_schema_ready():
        return _fallback_history(article)
    return tuple(
        AdminPublishedRevision(
            revision_id=row.revision_id,
            sequence=row.revision.sequence,
            title=row.revision.title,
            published_at=row.published_at,
            content_format=row.revision.content_format,
            visibility=row.revision.visibility,
            is_current=row.revision_id == article.published_revision_id,
        )
        for row in ArticlePublication.objects.select_related("revision")
        .filter(article=article)
        .order_by("-published_at", "-revision__sequence", "-id")
    )


def admin_published_revision_exists(*, article: Article, revision_id: str) -> bool:
    if not publication_history_schema_ready():
        return article.published_revision_id == revision_id
    return ArticlePublication.objects.filter(
        article=article,
        revision_id=revision_id,
    ).exists()


__all__ = [
    "AdminPublishedRevision",
    "admin_published_revision_exists",
    "admin_published_revision_history",
    "publication_history_schema_ready",
]
