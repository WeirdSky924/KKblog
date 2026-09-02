import logging
from dataclasses import dataclass

from django.db import DatabaseError

from apps.comments.public import article_comment_counts
from apps.content.public import (
    public_article_ids_by_author,
    visible_articles_by_author,
)

from ..profile_identity import ProfileIdentity, resolve_profile_identity
from .home import ArticleIndexPage, article_index_page
from .like_counts import article_like_counts
from .view_counts import article_view_counts

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PublicProfileStats:
    article_count: int
    view_count: int
    comment_count: int
    like_count: int
    available: bool = True


@dataclass(frozen=True, slots=True)
class PublicProfilePage:
    identity: ProfileIdentity
    index_page: ArticleIndexPage
    stats: PublicProfileStats | None = None


def public_profile_stats(*, account_id) -> PublicProfileStats:
    try:
        article_ids = public_article_ids_by_author(author_id=account_id)
        if not article_ids:
            return PublicProfileStats(0, 0, 0, 0)
        return PublicProfileStats(
            article_count=len(article_ids),
            view_count=sum(article_view_counts(article_ids=article_ids).values()),
            comment_count=sum(article_comment_counts(article_ids=article_ids).values()),
            like_count=sum(article_like_counts(article_ids=article_ids).values()),
        )
    except DatabaseError:
        logger.warning("Public profile statistics are unavailable", exc_info=True)
        return PublicProfileStats(0, 0, 0, 0, available=False)


def profile_article_page(
    *,
    actor_id,
    account_id,
    page: int = 1,
    page_size: int = 20,
    section_id=None,
    tag_ids=(),
    include_stats: bool = True,
) -> PublicProfilePage | None:
    identity = resolve_profile_identity(account_id)
    if identity is None:
        return None
    source = visible_articles_by_author(
        actor_id=actor_id,
        author_id=identity.account_id,
        page=page,
        page_size=page_size,
        section_id=section_id,
        tag_ids=tag_ids,
    )
    return PublicProfilePage(
        identity=identity,
        index_page=article_index_page(source),
        stats=public_profile_stats(account_id=identity.account_id)
        if include_stats
        else None,
    )
