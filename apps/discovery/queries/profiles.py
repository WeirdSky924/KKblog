from dataclasses import dataclass

from apps.content.public import visible_articles_by_author

from ..profile_identity import ProfileIdentity, resolve_profile_identity
from .home import ArticleIndexPage, article_index_page


@dataclass(frozen=True, slots=True)
class PublicProfilePage:
    identity: ProfileIdentity
    index_page: ArticleIndexPage


def profile_article_page(
    *,
    actor_id,
    account_id,
    page: int = 1,
    page_size: int = 20,
    section_id=None,
    tag_ids=(),
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
    return PublicProfilePage(identity=identity, index_page=article_index_page(source))
