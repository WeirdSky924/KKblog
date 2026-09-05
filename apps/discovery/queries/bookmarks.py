from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.templatetags.static import static

from apps.comments.public import article_comment_counts
from apps.content.public import visible_articles_by_ids
from apps.core.pagination import page_window
from apps.core.time import to_shanghai

from ..models import Bookmark
from ..profile_identity import resolve_profile_identities
from .home import ArticleIndexItem, article_index_item
from .like_counts import article_like_counts
from .view_counts import article_view_counts

ALLOWED_PAGE_SIZES = frozenset({10, 20, 50})


@dataclass(frozen=True, slots=True)
class UnavailableBookmarkItem:
    article_id: str
    label: str
    cover_url: str


@dataclass(frozen=True, slots=True)
class BookmarkPageItem:
    article_id: str
    created_at: datetime
    created_label: str
    article: ArticleIndexItem | None
    unavailable: UnavailableBookmarkItem | None


@dataclass(frozen=True, slots=True)
class BookmarkPage:
    items: tuple[BookmarkPageItem, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool
    page_window: tuple[int | None, ...]


def _account_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ValueError("account id must be a UUID") from None


def _page_number(value) -> int:
    if isinstance(value, bool):
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def bookmark_page(*, account_id, page: int = 1, page_size: int = 20) -> BookmarkPage:
    account = _account_id(account_id)
    if isinstance(page_size, bool) or page_size not in ALLOWED_PAGE_SIZES:
        raise ValueError("page size must be 10, 20, or 50")
    paginator = Paginator(Bookmark.objects.filter(account_id=account), page_size)
    selected = paginator.get_page(_page_number(page))
    rows = tuple(selected.object_list)
    visible = {
        item.article_id: item
        for item in visible_articles_by_ids(
            actor_id=account,
            article_ids=(row.article_id for row in rows),
        )
    }
    view_counts = article_view_counts(article_ids=visible)
    comment_counts = article_comment_counts(article_ids=visible)
    like_counts = article_like_counts(article_ids=visible)
    authors = resolve_profile_identities(
        tuple(dict.fromkeys(item.author_id for item in visible.values()))
    )
    items = tuple(
        _bookmark_item(
            row,
            visible,
            authors,
            view_counts,
            comment_counts,
            like_counts,
        )
        for row in rows
    )
    return BookmarkPage(
        items=items,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
        page_window=page_window(selected.number, paginator.num_pages),
    )


def _bookmark_item(
    row, visible, authors, view_counts, comment_counts, like_counts
) -> BookmarkPageItem:
    source = visible.get(row.article_id)
    created = to_shanghai(row.created_at)
    if source is None:
        article = None
        unavailable = UnavailableBookmarkItem(
            article_id=row.article_id,
            label="该文章已丢失",
            cover_url=static("media/brand/unavailable-bookmark.png"),
        )
    else:
        article = article_index_item(
            source,
            author=authors[source.author_id],
            view_count=view_counts.get(row.article_id, 0),
            comment_count=comment_counts.get(row.article_id, 0),
            like_count=like_counts.get(row.article_id, 0),
        )
        unavailable = None
    return BookmarkPageItem(
        article_id=row.article_id,
        created_at=row.created_at,
        created_label=created.strftime("%Y-%m-%d %H:%M"),
        article=article,
        unavailable=unavailable,
    )
