from dataclasses import dataclass
from uuid import UUID

from apps.content.public import (
    ArticleNotFound,
    article_for_author,
    revision_timeline,
)
from apps.core.ids import normalize_ulid
from apps.media.public import ArticleBodyMediaItem, owner_article_body_assets


@dataclass(frozen=True, slots=True)
class ArticleBodyMediaWorkspace:
    upload_scope: str
    article_id: str
    items: tuple[ArticleBodyMediaItem, ...]


def article_body_media_workspace(
    *,
    actor_id: UUID,
    upload_scope: str,
    article_id: str = "",
) -> ArticleBodyMediaWorkspace:
    try:
        normalized_scope = normalize_ulid(upload_scope)
    except (TypeError, ValueError):
        raise ArticleNotFound from None
    normalized_article = ""
    revision_ids: tuple[str, ...] = ()
    if article_id:
        try:
            normalized_article = normalize_ulid(article_id)
        except (TypeError, ValueError):
            raise ArticleNotFound from None
        article = article_for_author(
            actor_id=actor_id,
            article_id=normalized_article,
        )
        if not article.can_edit:
            raise ArticleNotFound
        revision_ids = tuple(
            item.revision_id
            for item in revision_timeline(
                actor_id=actor_id,
                article_id=normalized_article,
            )
        )
    return ArticleBodyMediaWorkspace(
        upload_scope=normalized_scope,
        article_id=normalized_article,
        items=owner_article_body_assets(
            owner_id=actor_id,
            upload_scope=normalized_scope,
            revision_ids=revision_ids,
        ),
    )
