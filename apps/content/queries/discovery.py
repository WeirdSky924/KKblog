from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from uuid import UUID

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, Prefetch, Q

from apps.accounts.public import is_active_account, is_active_author
from apps.media.public import render_markdown, render_tiptap

from ..models import Article, ArticleRevision, AuthorContentMask, RevisionTag, Tag
from ..policies import apply_article_reader_scope

ALLOWED_PAGE_SIZES = frozenset({10, 20, 50})
FILTERABLE_TAG_STATES = (Tag.State.ACTIVE, Tag.State.PENDING)


@dataclass(frozen=True, slots=True)
class VisibleArticleTag:
    tag_id: UUID
    name: str
    state: str


@dataclass(frozen=True, slots=True)
class VisibleArticleItem:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    summary: str | None
    visibility: str
    section_id: UUID | None
    section_name: str | None
    tags: tuple[VisibleArticleTag, ...]
    cover_asset_id: str | None
    published_at: datetime


@dataclass(frozen=True, slots=True)
class VisibleArticlePage:
    items: tuple[VisibleArticleItem, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool


def _actor_id(value) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ValueError("actor_id must be a UUID or None") from None


def _page_number(value) -> int:
    if isinstance(value, bool):
        return 1
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, number)


def _tag_ids(values) -> tuple[UUID, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise ValueError("tag ids must be UUID values")
    try:
        raw_values = tuple(values)
    except TypeError:
        raise ValueError("tag ids must be UUID values") from None
    normalized: list[UUID] = []
    for value in raw_values:
        try:
            identity = UUID(str(value))
        except (TypeError, ValueError):
            raise ValueError("tag ids must be UUID values") from None
        if identity not in normalized:
            normalized.append(identity)
    if len(normalized) > 5:
        raise ValueError("at most five tag ids may be selected")
    return tuple(normalized)


def _visible_articles(*, actor_id):
    actor = _actor_id(actor_id)
    authenticated = actor is not None and is_active_account(actor)
    visibility = Q(published_revision__visibility=ArticleRevision.Visibility.PUBLIC)
    if authenticated:
        visibility |= Q(
            published_revision__visibility=ArticleRevision.Visibility.AUTHENTICATED
        )
        if is_active_author(actor):
            visibility |= Q(
                author_id=actor,
                published_revision__visibility=ArticleRevision.Visibility.PRIVATE,
            )
    queryset = Article.objects.filter(
        visibility,
        publication_state=Article.PublicationState.PUBLISHED,
        published_at__isnull=False,
        published_revision__isnull=False,
        deleted_at__isnull=True,
        author__status="ACTIVE",
    ).exclude(
        author_id__in=AuthorContentMask.objects.filter(masked=True).values("author_id")
    )
    return apply_article_reader_scope(queryset)


def visible_filter_tags(*, actor_id) -> tuple[VisibleArticleTag, ...]:
    revision_ids = _visible_articles(actor_id=actor_id).values("published_revision_id")
    tags = (
        Tag.objects.filter(
            state__in=FILTERABLE_TAG_STATES,
            revision_snapshots__revision_id__in=revision_ids,
        )
        .distinct()
        .order_by("normalized_name", "id")
    )
    return tuple(VisibleArticleTag(tag.id, tag.name, tag.state) for tag in tags)


def _index_projection(queryset):
    tag_rows = (
        RevisionTag.objects.select_related("tag")
        .exclude(tag__state__in=(Tag.State.REJECTED, Tag.State.DELETED))
        .order_by("tag__normalized_name", "tag_id")
    )
    return queryset.select_related("published_revision__section").prefetch_related(
        Prefetch(
            "published_revision__tag_snapshots",
            queryset=tag_rows,
            to_attr="visible_index_tags",
        )
    )


def _visible_page(queryset, *, page, page_size: int) -> VisibleArticlePage:
    paginator = Paginator(_index_projection(queryset), page_size)
    selected = paginator.get_page(_page_number(page))
    return VisibleArticlePage(
        items=tuple(_visible_item(article) for article in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def visible_article_page(
    *,
    actor_id,
    page: int = 1,
    page_size: int = 20,
    section_id=None,
    tag_ids=(),
) -> VisibleArticlePage:
    if isinstance(page_size, bool) or page_size not in ALLOWED_PAGE_SIZES:
        raise ValueError("page size must be 10, 20, or 50")
    selected_tag_ids = _tag_ids(tag_ids)
    queryset = _visible_articles(actor_id=actor_id)
    if section_id is not None:
        try:
            section_identity = UUID(str(section_id))
        except (TypeError, ValueError):
            raise ValueError("section_id must be a UUID or None") from None
        queryset = queryset.filter(published_revision__section_id=section_identity)
    if selected_tag_ids:
        match_filter = Q(
            published_revision__tag_snapshots__tag_id__in=selected_tag_ids,
            published_revision__tag_snapshots__tag__state__in=(FILTERABLE_TAG_STATES),
        )
        queryset = queryset.filter(match_filter).annotate(
            matched_tag_count=Count(
                "published_revision__tag_snapshots__tag_id",
                filter=match_filter,
                distinct=True,
            )
        )
        queryset = queryset.order_by("-matched_tag_count", "-published_at", "-id")
    else:
        queryset = queryset.order_by("-published_at", "-id")
    return _visible_page(queryset, page=page, page_size=page_size)


def _search_query(value) -> str:
    if not isinstance(value, str):
        raise ValueError("query is required")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("query is required")
    if len(normalized) > 100:
        raise ValueError("query must not exceed 100 characters")
    return normalized


def _search_threshold(value) -> float:
    if isinstance(value, bool):
        raise ValueError("search threshold must be between 0 and 1")
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        raise ValueError("search threshold must be between 0 and 1") from None
    if not 0 < threshold <= 1:
        raise ValueError("search threshold must be between 0 and 1")
    return threshold


def search_visible_titles(
    *,
    actor_id,
    query: str,
    page: int = 1,
    page_size: int = 20,
    threshold=None,
) -> VisibleArticlePage:
    if isinstance(page_size, bool) or page_size not in ALLOWED_PAGE_SIZES:
        raise ValueError("page size must be 10, 20, or 50")
    normalized = _search_query(query)
    active_threshold = _search_threshold(
        settings.DISCOVERY_TITLE_SEARCH_THRESHOLD if threshold is None else threshold
    )
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('pg_trgm.similarity_threshold', %s, true)",
                [str(active_threshold)],
            )
        queryset = (
            _visible_articles(actor_id=actor_id)
            .filter(
                Q(published_revision__title__trigram_similar=normalized)
                | Q(published_revision__title__icontains=normalized)
            )
            .annotate(
                relevance=TrigramSimilarity("published_revision__title", normalized)
            )
            .order_by("-relevance", "-published_at", "-id")
        )
        return _visible_page(queryset, page=page, page_size=page_size)


def _visible_item(article: Article) -> VisibleArticleItem:
    revision = article.published_revision
    assert revision is not None
    assert article.published_at is not None
    section = revision.section
    return VisibleArticleItem(
        article_id=article.id,
        revision_id=revision.id,
        author_id=article.author_id,
        title=revision.title,
        summary=_card_summary(revision),
        visibility=revision.visibility,
        section_id=section.id if section else None,
        section_name=section.name if section else None,
        tags=tuple(
            VisibleArticleTag(row.tag_id, row.tag.name, row.tag.state)
            for row in revision.visible_index_tags
        ),
        cover_asset_id=revision.cover_asset_id,
        published_at=article.published_at,
    )


_BLOCK_TAGS = frozenset(
    {
        "blockquote",
        "br",
        "div",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "p",
        "pre",
        "table",
        "td",
        "th",
    }
)


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _card_summary(revision: ArticleRevision) -> str | None:
    if revision.summary_mode == ArticleRevision.SummaryMode.NONE:
        return None
    if revision.summary_mode == ArticleRevision.SummaryMode.CUSTOM:
        return revision.custom_summary
    if revision.content_format == ArticleRevision.ContentFormat.MARKDOWN:
        rendered = render_markdown(revision.body_markdown or "")
    else:
        rendered = render_tiptap(revision.body_tiptap or {})
    parser = _PlainTextParser()
    parser.feed(rendered.html)
    parser.close()
    plain_text = " ".join("".join(parser.parts).split())
    return plain_text[:100]
