from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.accounts.public import is_active_author
from apps.core.time.clock import Clock, SystemClock

from ..models import Article
from ..policies import article_is_reader_masked, author_is_content_masked
from .access import ArticleNotFound

AUTHOR_ARTICLE_STATES = ("PUBLISHED", "DRAFT", "SCHEDULED", "DELETED")
AUTHOR_PAGE_SIZES = frozenset({10, 20, 50})


@dataclass(frozen=True, slots=True)
class AuthorArticleCounts:
    published: int
    draft: int
    scheduled: int
    deleted: int

    @property
    def total(self) -> int:
        return self.published + self.draft + self.scheduled + self.deleted

    def for_state(self, state: str) -> int:
        values = {
            "PUBLISHED": self.published,
            "DRAFT": self.draft,
            "SCHEDULED": self.scheduled,
            "DELETED": self.deleted,
        }
        try:
            return values[state]
        except KeyError:
            raise ValueError("state must be an author article state") from None


@dataclass(frozen=True, slots=True)
class AuthorArticleItem:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    content_format: str
    visibility: str
    state: str
    sequence: int
    cover_asset_id: str | None
    updated_at: datetime
    published_at: datetime | None
    scheduled_for: datetime | None
    deleted_at: datetime | None
    purge_after: datetime | None
    row_version: int
    has_unpublished_changes: bool
    can_edit: bool
    can_review: bool
    can_restore: bool
    can_delete: bool


@dataclass(frozen=True, slots=True)
class AuthorArticlePage:
    items: tuple[AuthorArticleItem, ...]
    selected_state: str
    counts: AuthorArticleCounts
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool


def _state(value: str) -> str:
    if value not in AUTHOR_ARTICLE_STATES:
        raise ValueError("state must be an author article state")
    return value


def _page_number(value) -> int:
    if isinstance(value, bool):
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _actor(value) -> UUID:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleNotFound from None
    if not is_active_author(actor) or author_is_content_masked(actor):
        raise ArticleNotFound
    return actor


def authoring_access(actor_id) -> bool:
    try:
        actor = UUID(str(actor_id))
    except (TypeError, ValueError):
        return False
    return is_active_author(actor) and not author_is_content_masked(actor)


def _counts(queryset) -> AuthorArticleCounts:
    values = queryset.aggregate(
        published=Count(
            "id",
            filter=Q(
                deleted_at__isnull=True,
                publication_state=Article.PublicationState.PUBLISHED,
            ),
        ),
        draft=Count(
            "id",
            filter=Q(
                deleted_at__isnull=True,
                publication_state=Article.PublicationState.DRAFT,
            ),
        ),
        scheduled=Count(
            "id",
            filter=Q(
                deleted_at__isnull=True,
                publication_state=Article.PublicationState.SCHEDULED,
            ),
        ),
        deleted=Count("id", filter=Q(deleted_at__isnull=False)),
    )
    return AuthorArticleCounts(
        published=values["published"],
        draft=values["draft"],
        scheduled=values["scheduled"],
        deleted=values["deleted"],
    )


def _selected(queryset, state: str):
    if state == "DELETED":
        return queryset.filter(deleted_at__isnull=False).order_by("purge_after", "id")
    selected = queryset.filter(
        deleted_at__isnull=True,
        publication_state=state,
    )
    if state == "SCHEDULED":
        return selected.order_by("scheduled_for", "id")
    if state == "PUBLISHED":
        return selected.order_by("-last_published_at", "-updated_at", "-id")
    return selected.order_by("-updated_at", "-id")


def _item(article: Article, state: str) -> AuthorArticleItem:
    revision = article.working_revision
    if revision is None:
        raise RuntimeError("author article is missing its working revision")
    masked = article_is_reader_masked(article.id)
    editable = state != "DELETED" and not masked
    return AuthorArticleItem(
        article_id=article.id,
        revision_id=revision.id,
        author_id=article.author_id,
        title=revision.title,
        content_format=revision.content_format,
        visibility=revision.visibility,
        state=state,
        sequence=revision.sequence,
        cover_asset_id=revision.cover_asset_id,
        updated_at=article.updated_at,
        published_at=article.latest_published_at,
        scheduled_for=article.scheduled_for,
        deleted_at=article.deleted_at,
        purge_after=article.purge_after,
        row_version=article.row_version,
        has_unpublished_changes=(
            article.published_revision_id is not None
            and article.working_revision_id != article.published_revision_id
        ),
        can_edit=editable,
        can_review=editable,
        can_restore=state == "DELETED" and not masked,
        can_delete=editable,
    )


def author_article_page(
    *,
    actor_id,
    state: str = "PUBLISHED",
    page: int = 1,
    page_size: int = 20,
    clock: Clock | None = None,
) -> AuthorArticlePage:
    selected_state = _state(state)
    if isinstance(page_size, bool) or page_size not in AUTHOR_PAGE_SIZES:
        raise ValueError("page size must be 10, 20, or 50")
    actor = _actor(actor_id)
    now = (clock or SystemClock()).now()
    owned = Article.objects.filter(
        Q(deleted_at__isnull=True) | Q(purge_after__gt=now),
        author_id=actor,
        working_revision__isnull=False,
    ).select_related("working_revision")
    counts = _counts(owned)
    paginator = Paginator(_selected(owned, selected_state), page_size)
    selected = paginator.get_page(_page_number(page))
    return AuthorArticlePage(
        items=tuple(_item(article, selected_state) for article in selected.object_list),
        selected_state=selected_state,
        counts=counts,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )
