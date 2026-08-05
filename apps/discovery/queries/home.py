import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.templatetags.static import static
from redis.exceptions import RedisError

from apps.comments.public import article_comment_counts
from apps.content.public import (
    current_public_article_revisions,
    search_visible_titles,
    section_by_id,
    section_list,
    selectable_tag_list,
    tag_reference,
    visible_article_page,
    visible_filter_tags,
)
from apps.core.time import to_shanghai
from apps.discovery.cache import default_discovery_cache, list_query_hash

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


def _public_cached_source(*, kind: str, parameters: dict[str, object], loader):
    cache = default_discovery_cache()
    if cache is None:
        return loader()
    query_hash = list_query_hash(kind, parameters)
    generation = None
    try:
        generation = cache.list_generation()
        cached = cache.get_list(query_hash=query_hash, generation=generation)
    except RedisError:
        cached = None
    if cached is not None:
        current = {
            item.article_id: item.revision_id
            for item in current_public_article_revisions(
                article_ids=(item.article_id for item in cached.items)
            )
        }
        if len(current) == len(cached.items) and all(
            current.get(item.article_id) == item.revision_id for item in cached.items
        ):
            return cached
    source = loader()
    if generation is not None:
        try:
            cache.set_list(
                query_hash=query_hash,
                page=source,
                expected_generation=generation,
            )
        except RedisError:
            pass
    return source


def page_window(current: int, total: int) -> tuple[int | None, ...]:
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
    selected_tag_ids = tuple(tag_ids)

    def loader():
        return visible_article_page(
            actor_id=actor_id,
            page=page,
            page_size=page_size,
            tag_ids=selected_tag_ids,
        )

    source = (
        _public_cached_source(
            kind="home",
            parameters={
                "page": page,
                "page_size": page_size,
                "tag_ids": sorted(str(item) for item in selected_tag_ids),
            },
            loader=loader,
        )
        if actor_id is None
        else loader()
    )
    return article_index_page(source)


def search_article_page(
    *, actor_id, query: str, page: int = 1, page_size: int = 20
) -> ArticleIndexPage:
    def loader():
        return search_visible_titles(
            actor_id=actor_id, query=query, page=page, page_size=page_size
        )

    source = (
        _public_cached_source(
            kind="search",
            parameters={
                "query": unicodedata.normalize("NFKC", query).strip(),
                "page": page,
                "page_size": page_size,
            },
            loader=loader,
        )
        if actor_id is None
        else loader()
    )
    return article_index_page(source)


def discovery_filters(*, actor_id) -> DiscoveryFilters:
    return DiscoveryFilters(
        sections=tuple(
            DiscoveryFilterOption(item.section_id, item.name) for item in section_list()
        ),
        tags=tuple(
            DiscoveryFilterOption(item.tag_id, item.name, item.state)
            for item in selectable_tag_list()
        ),
    )


def section_article_page(
    *, actor_id, section_id, page: int = 1, page_size: int = 20
) -> ArticleCollectionPage | None:
    section = section_by_id(section_id)
    if section is None:
        return None

    def loader():
        return visible_article_page(
            actor_id=actor_id,
            page=page,
            page_size=page_size,
            section_id=section.section_id,
        )

    source = (
        _public_cached_source(
            kind="section",
            parameters={
                "section_id": str(section.section_id),
                "page": page,
                "page_size": page_size,
            },
            loader=loader,
        )
        if actor_id is None
        else loader()
    )
    return ArticleCollectionPage(section.name, None, article_index_page(source))


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

    def loader():
        return visible_article_page(
            actor_id=actor_id,
            page=page,
            page_size=page_size,
            tag_ids=(tag.tag_id,),
        )

    source = (
        _public_cached_source(
            kind="tag",
            parameters={
                "tag_id": str(tag.tag_id),
                "page": page,
                "page_size": page_size,
            },
            loader=loader,
        )
        if actor_id is None
        else loader()
    )
    return ArticleCollectionPage(tag.name, tag.state, article_index_page(source))


def article_index_page(source) -> ArticleIndexPage:
    article_ids = tuple(item.article_id for item in source.items)
    view_counts = article_view_counts(article_ids=article_ids)
    comment_counts = article_comment_counts(article_ids=article_ids)
    items = tuple(
        article_index_item(
            item,
            view_count=view_counts.get(item.article_id, 0),
            comment_count=comment_counts.get(item.article_id, 0),
        )
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
        page_window=page_window(source.page_number, source.total_pages),
    )


def article_index_item(
    source, *, view_count: int, comment_count: int
) -> ArticleIndexItem:
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
        comment_count=comment_count,
    )
