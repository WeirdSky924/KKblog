from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.templatetags.static import static

from apps.content.public import (
    search_visible_titles,
    section_by_id,
    section_list,
    tag_reference,
    visible_article_page,
    visible_filter_tags,
)
from apps.core.time import to_shanghai

from .view_counts import article_view_counts


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


@dataclass(frozen=True, slots=True)
class DiscoveryFilterOption:
    filter_id: UUID
    name: str
    state: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryFilters:
    sections: tuple[DiscoveryFilterOption, ...]
    tags: tuple[DiscoveryFilterOption, ...]


@dataclass(frozen=True, slots=True)
class ArticleCollectionPage:
    name: str
    state: str | None
    index_page: ArticleIndexPage


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
    *, actor_id, page: int = 1, page_size: int = 20, tag_ids=()
) -> ArticleIndexPage:
    source = visible_article_page(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
        tag_ids=tag_ids,
    )
    return _index_page(source)


def search_article_page(
    *, actor_id, query: str, page: int = 1, page_size: int = 20
) -> ArticleIndexPage:
    source = search_visible_titles(
        actor_id=actor_id,
        query=query,
        page=page,
        page_size=page_size,
    )
    return _index_page(source)


def discovery_filters(*, actor_id) -> DiscoveryFilters:
    return DiscoveryFilters(
        sections=tuple(
            DiscoveryFilterOption(item.section_id, item.name) for item in section_list()
        ),
        tags=tuple(
            DiscoveryFilterOption(item.tag_id, item.name, item.state)
            for item in visible_filter_tags(actor_id=actor_id)
        ),
    )


def section_article_page(
    *, actor_id, section_id, page: int = 1, page_size: int = 20
) -> ArticleCollectionPage | None:
    section = section_by_id(section_id)
    if section is None:
        return None
    source = visible_article_page(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
        section_id=section.section_id,
    )
    return ArticleCollectionPage(section.name, None, _index_page(source))


def tag_article_page(
    *, actor_id, tag_id, page: int = 1, page_size: int = 20
) -> ArticleCollectionPage | None:
    tag = tag_reference(tag_id)
    if tag is None:
        return None
    if tag.state == "REJECTED":
        return None
    if tag.state == "PENDING" and tag.tag_id not in {
        item.tag_id for item in visible_filter_tags(actor_id=actor_id)
    }:
        return None
    source = visible_article_page(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
        tag_ids=(tag.tag_id,),
    )
    return ArticleCollectionPage(tag.name, tag.state, _index_page(source))


def _index_page(source) -> ArticleIndexPage:
    view_counts = article_view_counts(
        article_ids=(item.article_id for item in source.items)
    )
    items = tuple(
        _index_item(item, view_count=view_counts.get(item.article_id, 0))
        for item in source.items
    )
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


def _index_item(source, *, view_count: int) -> ArticleIndexItem:
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
        view_count=view_count,
        comment_count=0,
    )
