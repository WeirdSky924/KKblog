from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Q

from apps.accounts.public import is_administrator
from apps.core.ids import normalize_ulid

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


@dataclass(frozen=True, slots=True)
class AdminArticleTitle:
    id: str
    title: str


def _keyword(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid administrator article query")
    normalized = value.strip()
    if len(normalized) > 100:
        raise ValueError("Invalid administrator article query")
    return normalized


def _item(article: Article) -> AdminArticleItem | None:
    revision = article.working_revision or article.published_revision
    if revision is None:
        return None
    active = article.deleted_at is None
    published = (
        active
        and article.publication_state == Article.PublicationState.PUBLISHED
        and article.published_revision_id is not None
    )
    return AdminArticleItem(
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


def admin_article_item(*, actor_id, article_id: str) -> AdminArticleItem:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator article access denied")
    article = (
        Article.objects.select_related("working_revision", "published_revision")
        .filter(pk=article_id)
        .first()
    )
    item = _item(article) if article is not None else None
    if item is None:
        raise LookupError("Administrator article not found")
    return item


def admin_article_titles(
    *, actor_id, article_ids: tuple[str, ...]
) -> tuple[AdminArticleTitle, ...]:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator article access denied")
    if not isinstance(article_ids, tuple) or len(article_ids) > 500:
        raise ValueError("Invalid administrator article identities")
    try:
        identities = tuple(
            dict.fromkeys(normalize_ulid(value) for value in article_ids)
        )
    except (TypeError, ValueError):
        raise ValueError("Invalid administrator article identities") from None
    rows = Article.objects.select_related(
        "working_revision", "published_revision"
    ).filter(pk__in=identities)
    return tuple(
        AdminArticleTitle(id=item.id, title=item.title)
        for article in rows
        if (item := _item(article)) is not None
    )


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
    items = [item for article in rows if (item := _item(article)) is not None]
    return tuple(items)


__all__ = [
    "ADMIN_ARTICLE_STATES",
    "AdminArticleItem",
    "AdminArticleTitle",
    "admin_article_item",
    "admin_article_page",
    "admin_article_titles",
]
