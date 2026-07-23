from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.templatetags.static import static

from apps.content.public import visible_article_page
from apps.core.time import to_shanghai


@dataclass(frozen=True, slots=True)
class ArticleIndexTag:
    tag_id: UUID
    name: str
    state: str


@dataclass(frozen=True, slots=True)
class ArticleIndexItem:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    summary: str | None
    section_id: UUID | None
    section_name: str | None
    tags: tuple[ArticleIndexTag, ...]
    cover_url: str
    uses_default_cover: bool
    published_at: datetime
    published_label: str
    visibility: str
    view_count: int
    comment_count: int


@dataclass(frozen=True, slots=True)
class ArticleIndexPage:
    items: tuple[ArticleIndexItem, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool
    page_window: tuple[int | None, ...]


def _page_window(current: int, total: int) -> tuple[int | None, ...]:
    visible = {1, total, *(range(max(1, current - 2), min(total, current + 2) + 1))}
    ordered = sorted(number for number in visible if 1 <= number <= total)
    result: list[int | None] = []
    previous = 0
    for number in ordered:
        if previous and number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return tuple(result)


def home_article_page(
    *, actor_id, page: int = 1, page_size: int = 20
) -> ArticleIndexPage:
    source = visible_article_page(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
    )
    items = tuple(_index_item(item) for item in source.items)
    return ArticleIndexPage(
        items=items,
        page_number=source.page_number,
        page_size=source.page_size,
        total_items=source.total_items,
        total_pages=source.total_pages,
        has_previous=source.has_previous,
        has_next=source.has_next,
        page_window=_page_window(source.page_number, source.total_pages),
    )


def _index_item(source) -> ArticleIndexItem:
    published = to_shanghai(source.published_at)
    return ArticleIndexItem(
        article_id=source.article_id,
        revision_id=source.revision_id,
        author_id=source.author_id,
        title=source.title,
        summary=source.summary,
        section_id=source.section_id,
        section_name=source.section_name,
        tags=tuple(
            ArticleIndexTag(tag.tag_id, tag.name, tag.state) for tag in source.tags
        ),
        cover_url=(
            f"/_kaj/media/{source.cover_asset_id}"
            if source.cover_asset_id
            else static("media/brand/default-cover.png")
        ),
        uses_default_cover=source.cover_asset_id is None,
        published_at=source.published_at,
        published_label=published.strftime("%Y-%m-%d %H:%M"),
        visibility=source.visibility,
        view_count=0,
        comment_count=0,
    )
