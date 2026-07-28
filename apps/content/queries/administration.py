from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q

from apps.accounts.public import is_administrator

from ..models import Article

ADMIN_ARTICLE_STATES = ("DRAFT", "SCHEDULED", "PUBLISHED", "DELETED")


@dataclass(frozen=True, slots=True)
class AdminArticleItem:
    id: str
    author_id: UUID
    title: str
    publication_state: str
    visibility: str
    deleted_at: datetime | None
    purge_after: datetime | None
    published_at: datetime | None
    updated_at: datetime
    has_working_revision: bool
    has_published_revision: bool
    can_hide: bool
    can_delete: bool
    can_restore_deleted: bool


def _keyword(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid administrator article query")
    normalized = value.strip()
    if len(normalized) > 100:
        raise ValueError("Invalid administrator article query")
    return normalized


def admin_article_page(
    *, actor_id, query: str = "", state: str = "", limit: int = 200
) -> tuple[AdminArticleItem, ...]:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator article access denied")
    keyword = _keyword(query)
    if state and state not in ADMIN_ARTICLE_STATES:
        raise ValueError("Invalid administrator article state")
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator article limit")

    queryset = Article.objects.select_related(
        "working_revision",
        "published_revision",
    )
    if keyword:
        queryset = queryset.filter(
            Q(working_revision__title__icontains=keyword)
            | Q(published_revision__title__icontains=keyword)
            | Q(author__email__icontains=keyword)
            | Q(author__nickname__icontains=keyword)
        )
    if state == "DELETED":
        queryset = queryset.filter(deleted_at__isnull=False)
    elif state:
        queryset = queryset.filter(
            deleted_at__isnull=True,
            publication_state=state,
        )

    rows = queryset.order_by("-updated_at", "-id")[:limit]
    items = []
    for article in rows:
        revision = article.working_revision or article.published_revision
        if revision is None:
            continue
        active = article.deleted_at is None
        published = (
            active
            and article.publication_state == Article.PublicationState.PUBLISHED
            and article.published_revision_id is not None
        )
        items.append(
            AdminArticleItem(
                id=article.id,
                author_id=article.author_id,
                title=revision.title,
                publication_state=article.publication_state,
                visibility=revision.visibility,
                deleted_at=article.deleted_at,
                purge_after=article.purge_after,
                published_at=article.published_at,
                updated_at=article.updated_at,
                has_working_revision=article.working_revision_id is not None,
                has_published_revision=article.published_revision_id is not None,
                can_hide=published,
                can_delete=active,
                can_restore_deleted=not active,
            )
        )
    return tuple(items)


__all__ = ["ADMIN_ARTICLE_STATES", "AdminArticleItem", "admin_article_page"]
