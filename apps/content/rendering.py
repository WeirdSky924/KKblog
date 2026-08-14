from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from html.parser import HTMLParser
from time import perf_counter
from typing import Any

from apps.media.public import (
    CURRENT_TIPTAP_SCHEMA_VERSION,
    NormalizedTipTapDocument,
    RenderingError,
    TipTapAttachmentMetadata,
    TipTapSchemaError,
    TrustedEmbedPolicy,
    normalize_tiptap_document,
    render_markdown,
    render_tiptap,
)
from apps.operations.public import record_rich_text_render_metric

from .rendering_policy import configured_content_embed_policy
from .snapshots import ContentFormat


class ArticleRenderingMode(StrEnum):
    STRICT = "strict"
    READER = "reader"
    SUMMARY = "summary"
    EXPORT = "export"


@dataclass(frozen=True, slots=True)
class ArticleBodyProjection:
    html: str
    plain_text: str
    readable_markdown: str
    sanitizer_version: str
    cache_key: str
    block_start_lines: tuple[int, ...]


MARKDOWN_SUMMARY_MAX_BYTES = 4 * 1024


_BLOCK_TAGS = frozenset(
    {
        "blockquote",
        "br",
        "aside",
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
        "span",
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


def sanitized_article_plain_text(html: str) -> str:
    if not isinstance(html, str):
        raise TypeError("sanitized article body must be text")
    parser = _PlainTextParser()
    parser.feed(html)
    parser.close()
    return " ".join("".join(parser.parts).split())


class _ReadableMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.lists: list[dict[str, int | str]] = []
        self.pre_content: list[str] | None = None
        self.pre_language = ""
        self.table_cell = 0

    def _newlines(self, count: int) -> None:
        if not self.parts:
            return
        tail = self.parts[-1]
        missing = count - (len(tail) - len(tail.rstrip("\n")))
        if missing > 0:
            self.parts.append("\n" * missing)

    def _current_line(self) -> str:
        fragments: list[str] = []
        for part in reversed(self.parts):
            if "\n" in part:
                fragments.append(part.rsplit("\n", 1)[-1])
                break
            fragments.append(part)
        return "".join(reversed(fragments))

    def _list_prefix(self) -> str:
        if not self.lists:
            return "- "
        current = self.lists[-1]
        indent = "  " * (len(self.lists) - 1)
        if current["kind"] == "ol":
            value = int(current["next"])
            current["next"] = value + 1
            return f"{indent}{value}. "
        return f"{indent}- "

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if self.pre_content is not None:
            if tag == "code":
                self.pre_language = attributes.get("data-language", "")
            return
        if tag == "pre":
            self._newlines(2)
            self.pre_content = []
            self.pre_language = ""
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._newlines(2)
            self.parts.append(f"{'#' * int(tag[1])} ")
        elif tag == "p":
            current_line = self._current_line()
            if not re.fullmatch(r"\s*(?:-|\d+\.) ", current_line):
                self._newlines(2)
        elif tag in {"blockquote", "aside", "table"}:
            self._newlines(2)
        elif tag in {"ul", "ol"}:
            self._newlines(1)
            start = attributes.get("start", "1")
            self.lists.append(
                {
                    "kind": tag,
                    "next": int(start)
                    if str(start).isdigit() and int(start) > 0
                    else 1,
                }
            )
        elif tag == "li":
            self._newlines(1)
            self.parts.append(self._list_prefix())
        elif tag == "tr":
            self._newlines(1)
            self.table_cell = 0
        elif tag in {"td", "th"}:
            if self.table_cell:
                self.parts.append(" | ")
            self.table_cell += 1
        elif tag == "br":
            self._newlines(1)
        elif tag == "hr":
            self._newlines(2)
            self.parts.append("---")
            self._newlines(2)

    def handle_endtag(self, tag: str) -> None:
        if self.pre_content is not None:
            if tag != "pre":
                return
            source = "".join(self.pre_content).rstrip("\n")
            longest = max((len(item) for item in re.findall(r"`+", source)), default=0)
            fence = "`" * max(3, longest + 1)
            language = self.pre_language if self.pre_language.isalnum() else ""
            self.parts.append(f"{fence}{language}\n{source}\n{fence}")
            self.pre_content = None
            self.pre_language = ""
            self._newlines(2)
            return
        if tag == "p":
            self._newlines(1 if self.lists else 2)
        elif tag in {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "aside",
            "table",
        }:
            self._newlines(2)
        elif tag == "li":
            self._newlines(1)
        elif tag in {"ul", "ol"}:
            if self.lists:
                self.lists.pop()
            self._newlines(2)
        elif tag == "tr":
            self._newlines(1)

    def handle_data(self, data: str) -> None:
        if self.pre_content is not None:
            self.pre_content.append(data)
        else:
            self.parts.append(escape(data, quote=False))

    def markdown(self) -> str:
        lines: list[str] = []
        previous_blank = True
        for source in "".join(self.parts).splitlines():
            line = " ".join(source.split())
            if line:
                lines.append(line)
                previous_blank = False
            elif not previous_blank:
                lines.append("")
                previous_blank = True
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)


def sanitized_article_readable_markdown(html: str) -> str:
    if not isinstance(html, str):
        raise TypeError("sanitized article body must be text")
    parser = _ReadableMarkdownParser()
    parser.feed(html)
    parser.close()
    return parser.markdown()


def _markdown_summary_source(source: str) -> str:
    encoded = source.encode("utf-8")
    if len(encoded) <= MARKDOWN_SUMMARY_MAX_BYTES:
        return source
    return encoded[:MARKDOWN_SUMMARY_MAX_BYTES].decode("utf-8", errors="ignore")


def normalize_article_tiptap_body(
    body: dict[str, Any],
    *,
    schema_version: int,
    mode: ArticleRenderingMode | str = ArticleRenderingMode.STRICT,
) -> NormalizedTipTapDocument:
    try:
        normalized_mode = ArticleRenderingMode(mode)
    except (TypeError, ValueError):
        raise RenderingError("Article rendering options are invalid") from None
    started = perf_counter()
    try:
        return normalize_tiptap_document(body, schema_version=schema_version)
    except (RenderingError, TypeError, ValueError, RecursionError) as error:
        record_rich_text_render_metric(
            content_format=ContentFormat.TIPTAP_JSON.value,
            mode=normalized_mode.value,
            schema_version=(
                schema_version
                if type(schema_version) is int and schema_version in {1, 2}
                else None
            ),
            source_bytes=0,
            node_count=0,
            max_depth=0,
            table_cells=0,
            duration_ms=min((perf_counter() - started) * 1000, 600_000),
            outcome="rejected",
            error_code=(
                error.code
                if isinstance(error, TipTapSchemaError)
                else "media.rendering_invalid.v1"
            ),
        )
        raise


def render_article_body(
    *,
    content_format: ContentFormat | str,
    body: str | dict[str, Any] | NormalizedTipTapDocument,
    tiptap_schema_version: int | None = None,
    allowed_media_ids=(),
    allowed_attachment_id: str | None = None,
    attachment_metadata: TipTapAttachmentMetadata | None = None,
    mode: ArticleRenderingMode | str = ArticleRenderingMode.STRICT,
) -> ArticleBodyProjection:
    try:
        normalized_format = ContentFormat(content_format)
        normalized_mode = ArticleRenderingMode(mode)
    except (TypeError, ValueError):
        raise RenderingError("Article rendering options are invalid") from None

    started = perf_counter()
    rendered = None
    failure: Exception | None = None
    try:
        policy = configured_content_embed_policy()
        unavailable_resources = "reject"
        if normalized_mode is ArticleRenderingMode.READER:
            unavailable_resources = "placeholder"
        elif normalized_mode in {
            ArticleRenderingMode.SUMMARY,
            ArticleRenderingMode.EXPORT,
        }:
            unavailable_resources = "omit"
            allowed_media_ids = ()
            allowed_attachment_id = None
            attachment_metadata = None
            policy = TrustedEmbedPolicy(enabled_sources=())

        if normalized_format == ContentFormat.MARKDOWN:
            if not isinstance(body, str):
                raise RenderingError("Markdown source must be text")
            render_source = (
                _markdown_summary_source(body)
                if normalized_mode is ArticleRenderingMode.SUMMARY
                else body
            )
            rendered = render_markdown(
                render_source,
                embed_policy=policy,
                allowed_media_ids=allowed_media_ids,
            )
        else:
            if not isinstance(body, dict | NormalizedTipTapDocument):
                raise RenderingError("TipTap source must be an object")
            rendered = render_tiptap(
                body,
                schema_version=(
                    tiptap_schema_version
                    if tiptap_schema_version is not None
                    else CURRENT_TIPTAP_SCHEMA_VERSION
                ),
                embed_policy=policy,
                allowed_media_ids=allowed_media_ids,
                allowed_attachment_id=allowed_attachment_id,
                attachment_metadata=attachment_metadata,
                unavailable_resources=unavailable_resources,
            )

        return ArticleBodyProjection(
            html=rendered.html,
            plain_text=sanitized_article_plain_text(rendered.html),
            readable_markdown=(
                body
                if normalized_mode is ArticleRenderingMode.EXPORT
                and normalized_format is ContentFormat.MARKDOWN
                else sanitized_article_readable_markdown(rendered.html)
                if normalized_mode is ArticleRenderingMode.EXPORT
                else ""
            ),
            sanitizer_version=rendered.sanitizer_version,
            cache_key=rendered.cache_key,
            block_start_lines=rendered.block_start_lines,
        )
    except Exception as error:
        failure = error
        raise
    finally:
        source_bytes = rendered.source_bytes if rendered is not None else 0
        if rendered is None and isinstance(body, str):
            try:
                source_bytes = min(len(body.encode("utf-8")), 64 * 1024 * 1024)
            except UnicodeEncodeError:
                source_bytes = 0
        rejected = isinstance(
            failure,
            (RenderingError, TypeError, ValueError, RecursionError),
        )
        error_code = "-"
        if isinstance(failure, TipTapSchemaError):
            error_code = failure.code
        elif failure is not None:
            error_code = (
                "media.rendering_invalid.v1" if rejected else "media.rendering_error.v1"
            )
        record_rich_text_render_metric(
            content_format=normalized_format.value,
            mode=normalized_mode.value,
            schema_version=(
                tiptap_schema_version
                if type(tiptap_schema_version) is int
                and tiptap_schema_version in {1, 2}
                else None
            ),
            source_bytes=source_bytes,
            node_count=rendered.node_count if rendered is not None else 0,
            max_depth=rendered.max_depth if rendered is not None else 0,
            table_cells=rendered.table_cells if rendered is not None else 0,
            duration_ms=min((perf_counter() - started) * 1000, 600_000),
            outcome=(
                "success" if failure is None else "rejected" if rejected else "error"
            ),
            error_code=error_code,
        )


__all__ = [
    "ArticleBodyProjection",
    "ArticleRenderingMode",
    "normalize_article_tiptap_body",
    "render_article_body",
    "sanitized_article_plain_text",
    "sanitized_article_readable_markdown",
]
