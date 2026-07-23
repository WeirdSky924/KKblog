from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.accounts.public import is_active_author
from apps.core.ids import normalize_ulid

from ..models import Article, ArticleRevision
from .access import ArticleNotFound


@dataclass(frozen=True, slots=True)
class RevisionTimelineItem:
    revision_id: str
    sequence: int
    created_at: datetime
    content_format: str
    visibility: str
    based_on_id: str | None
    restore_source_id: str | None
    is_working: bool
    is_published: bool
    is_scheduled: bool


def revision_timeline(*, actor_id, article_id: str) -> tuple[RevisionTimelineItem, ...]:
    try:
        actor = UUID(str(actor_id))
        identity = normalize_ulid(article_id)
    except (TypeError, ValueError):
        raise ArticleNotFound from None
    if not is_active_author(actor):
        raise ArticleNotFound
    try:
        article = Article.objects.get(pk=identity, author_id=actor)
    except Article.DoesNotExist:
        raise ArticleNotFound from None
    return tuple(
        RevisionTimelineItem(
            revision.id,
            revision.sequence,
            revision.created_at,
            revision.content_format,
            revision.visibility,
            revision.based_on_id,
            revision.restore_source_id,
            revision.id == article.working_revision_id,
            revision.id == article.published_revision_id,
            revision.id == article.scheduled_revision_id,
        )
        for revision in ArticleRevision.objects.filter(article=article).order_by(
            "-sequence"
        )
    )
