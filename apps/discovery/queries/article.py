from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from uuid import UUID

from django.templatetags.static import static
from django.utils.safestring import SafeString, mark_safe
from redis.exceptions import RedisError

from apps.content.public import (
    ArticleNotFound,
    article_for_reader,
    public_article_cache_snapshot,
    render_public_article_body,
)
from apps.core.time import to_shanghai
from apps.discovery.cache import default_discovery_cache
from apps.discovery.seo import ArticleSeoMetadata, article_seo_metadata


@dataclass(frozen=True, slots=True)
class ArticleTocItem:
    anchor: str
    label: str


@dataclass(frozen=True, slots=True)
class ArticleDetailPage:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    visibility: str
    body_html: SafeString
    toc: tuple[ArticleTocItem, ...]
    cover_url: str
    uses_default_cover: bool
    published_at: datetime
    published_label: str
    seo: ArticleSeoMetadata


class _H2TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_h2 = False
        self._parts: list[str] = []
        self.labels: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag == "h2":
            self._inside_h2 = True
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._inside_h2:
            self.labels.append(" ".join("".join(self._parts).split()))
            self._inside_h2 = False
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_h2:
            self._parts.append(data)


def _start_tag(
    tag: str,
    attrs: list[tuple[str, str | None]],
    *,
    heading_id: str | None = None,
) -> str:
    parts = [f"<{tag}"]
    for name, value in attrs:
        if name == "id" and heading_id is not None:
            continue
        parts.append(f" {name}")
        if value is not None:
            parts.append(f'="{escape(value, quote=True)}"')
    if heading_id is not None:
        parts.append(f' id="{heading_id}"')
    parts.append(">")
    return "".join(parts)


class _HeadingIdParser(HTMLParser):
    def __init__(self, heading_ids: tuple[str | None, ...]) -> None:
        super().__init__(convert_charrefs=False)
        self._heading_ids = heading_ids
        self._heading_index = 0
        self._parts: list[str] = []

    @property
    def html(self) -> str:
        return "".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        heading_id = None
        if tag == "h2":
            if self._heading_index < len(self._heading_ids):
                heading_id = self._heading_ids[self._heading_index]
            self._heading_index += 1
        self._parts.append(_start_tag(tag, attrs, heading_id=heading_id))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")


def _outline(html: str) -> tuple[SafeString, tuple[ArticleTocItem, ...]]:
    text_parser = _H2TextParser()
    text_parser.feed(html)
    text_parser.close()
    heading_ids: list[str | None] = []
    toc: list[ArticleTocItem] = []
    for label in text_parser.labels:
        if not label:
            heading_ids.append(None)
            continue
        anchor = f"article-section-{len(toc) + 1}"
        heading_ids.append(anchor)
        toc.append(ArticleTocItem(anchor, label))
    id_parser = _HeadingIdParser(tuple(heading_ids))
    id_parser.feed(html)
    id_parser.close()
    return mark_safe(id_parser.html), tuple(toc)


def _same_public_revision(left, right) -> bool:
    return (
        left.article_id == right.article_id
        and left.revision_id == right.revision_id
        and left.sanitizer_version == right.sanitizer_version
    )


def _cached_public_article(article_id: str):
    cache = default_discovery_cache()
    for _attempt in range(2):
        snapshot = public_article_cache_snapshot(article_id=article_id)
        body_html = None
        generation = None
        if cache is not None:
            try:
                generation = cache.article_generation(snapshot.article_id)
                body_html = cache.get_article_body(
                    article_id=snapshot.article_id,
                    revision_id=snapshot.revision_id,
                    sanitizer_version=snapshot.sanitizer_version,
                    generation=generation,
                )
            except RedisError:
                body_html = None
        if body_html is not None:
            verified = public_article_cache_snapshot(article_id=article_id)
            if _same_public_revision(snapshot, verified):
                return verified, body_html
            continue

        rendered = render_public_article_body(
            article_id=snapshot.article_id,
            revision_id=snapshot.revision_id,
        )
        verified = public_article_cache_snapshot(article_id=article_id)
        if not _same_public_revision(snapshot, verified):
            continue
        if rendered.sanitizer_version != verified.sanitizer_version:
            raise RuntimeError("article sanitizer version changed during rendering")
        if cache is not None and generation is not None:
            try:
                cache.set_article_body(
                    article_id=verified.article_id,
                    revision_id=verified.revision_id,
                    sanitizer_version=verified.sanitizer_version,
                    html=rendered.html,
                    expected_generation=generation,
                )
            except RedisError:
                pass
        return verified, rendered.html
    raise ArticleNotFound


def article_detail_page(*, actor_id, article_id: str) -> ArticleDetailPage:
    try:
        source, sanitized_html = _cached_public_article(article_id)
        indexable = True
    except ArticleNotFound:
        source = article_for_reader(actor_id=actor_id, article_id=article_id)
        if source.rendered_body_html is None:
            raise RuntimeError("reader article is missing rendered body") from None
        sanitized_html = source.rendered_body_html
        indexable = False
    body_html, toc = _outline(sanitized_html)
    cover_asset_id = source.readable_cover_asset_id
    if source.published_at is None:
        raise RuntimeError("published article is missing publication time")
    published = to_shanghai(source.published_at)
    return ArticleDetailPage(
        article_id=source.article_id,
        revision_id=source.revision_id,
        author_id=source.author_id,
        title=source.title,
        visibility=source.visibility,
        body_html=body_html,
        toc=toc,
        cover_url=(
            f"/_kaj/media/{cover_asset_id}"
            if cover_asset_id
            else static("media/brand/default-cover.png")
        ),
        uses_default_cover=cover_asset_id is None,
        published_at=source.published_at,
        published_label=published.strftime("%Y-%m-%d %H:%M"),
        seo=article_seo_metadata(
            title=source.title,
            sanitized_body_html=sanitized_html,
            indexable=indexable,
        ),
    )
