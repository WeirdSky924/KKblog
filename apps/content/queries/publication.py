from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apps.accounts.public import is_active_account, is_active_author
from apps.core.ids import normalize_ulid

from ..models import Article, ArticleRevision
from ..policies import author_is_content_masked


@dataclass(frozen=True, slots=True)
class PublishedRevision:
    id: str
    article_id: str
    title: str
    content_format: str
    body_markdown: str | None
    body_tiptap: dict[str, Any] | None
    tiptap_schema_version: int | None
    visibility: str


def published_revision(
    article_id: str, *, actor_id: UUID | None = None
) -> PublishedRevision | None:
    try:
        identity = normalize_ulid(article_id)
    except (TypeError, ValueError):
        return None
    try:
        article = Article.objects.select_related("published_revision").get(
            pk=identity,
            deleted_at__isnull=True,
            published_revision__isnull=False,
        )
    except Article.DoesNotExist:
        return None
    revision = article.published_revision
    if (
        revision is None
        or not is_active_account(article.author_id)
        or author_is_content_masked(article.author_id)
    ):
        return None
    if revision.visibility == ArticleRevision.Visibility.PUBLIC:
        allowed = True
    elif revision.visibility == ArticleRevision.Visibility.AUTHENTICATED:
        allowed = actor_id is not None and is_active_account(actor_id)
    else:
        allowed = actor_id == article.author_id and is_active_author(actor_id)
    if not allowed:
        return None
    return PublishedRevision(
        revision.id,
        article.id,
        revision.title,
        revision.content_format,
        revision.body_markdown,
        revision.body_tiptap,
        revision.tiptap_schema_version,
        revision.visibility,
    )
