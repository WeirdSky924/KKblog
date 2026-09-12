from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from apps.accounts.public import is_active_account
from apps.content.public import (
    ArticleLoginRequired,
    ArticleNotFound,
    visible_articles_by_ids,
)

from .article import article_detail_page

MAX_SELECTION_INPUT_BYTES = 256 * 1024
DEFAULT_SELECTION_LIMIT = 1_000
MAX_SELECTION_LIMIT = 10_000

_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "pre",
        "section",
        "tr",
        "ul",
        "ol",
    }
)
_IGNORED_CONTAINERS = frozenset(
    {
        "audio",
        "canvas",
        "iframe",
        "object",
        "picture",
        "script",
        "style",
        "svg",
        "template",
        "video",
    }
)
_IGNORED_VOID = frozenset(
    {
        "area",
        "base",
        "col",
        "embed",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
    }
)
_TABLE_CELLS = frozenset({"td", "th"})
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_SPACE_RE = re.compile(r"[^\S\n]+")


class ArticleExplanationSelectionError(ValueError):
    """Raised when selection input cannot be safely used for an explanation."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "discovery.article_explanation_selection_invalid.v1",
    ):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CleanArticleSelection:
    text: str
    original_char_count: int
    processed_char_count: int
    was_truncated: bool


@dataclass(frozen=True, slots=True)
class ArticleExplanationContext:
    article_id: str
    article_title: str
    article_summary: str
    article_tags: tuple[str, ...]
    section_heading: str
    selected_text: str
    original_char_count: int
    processed_char_count: int
    was_truncated: bool


class _SelectionHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0
        self._row_cells = 0

    def _boundary(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.casefold()
        if self._ignored_depth:
            if normalized not in _IGNORED_VOID:
                self._ignored_depth += 1
            return
        attributes = {name.casefold(): value or "" for name, value in attrs}
        if normalized in _IGNORED_CONTAINERS:
            self._ignored_depth = 1
            return
        if normalized in _IGNORED_VOID:
            return
        if normalized == "div" and attributes.get("data-kaj-latex") == "true":
            source = attributes.get("data-kaj-latex-source", "")
            if source:
                self._boundary()
                self.parts.append(source)
                self._boundary()
            self._ignored_depth = 1
            return
        if normalized == "br":
            self._boundary()
        elif normalized == "tr":
            self._boundary()
            self._row_cells = 0
        elif normalized in _TABLE_CELLS:
            if self._row_cells:
                self.parts.append(" | ")
            self._row_cells += 1
        elif normalized in _BLOCK_TAGS:
            self._boundary()

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if self._ignored_depth:
            if normalized not in _IGNORED_VOID:
                self._ignored_depth -= 1
            return
        if normalized == "tr" or normalized in _BLOCK_TAGS:
            self._boundary()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def _validate_text(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ArticleExplanationSelectionError(f"{label}必须是文本。")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ArticleExplanationSelectionError(f"{label}包含无效字符。") from None
    if size > MAX_SELECTION_INPUT_BYTES:
        raise ArticleExplanationSelectionError(f"{label}输入过大。")
    return value


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _CONTROL_RE.sub("", normalized)
    normalized = "".join(
        character for character in normalized if unicodedata.category(character) != "Cf"
    )
    lines = []
    for line in normalized.split("\n"):
        cleaned = _SPACE_RE.sub(" ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _source_text(value: str, *, source: Literal["html", "text"]) -> str:
    if source == "text":
        return value
    parser = _SelectionHTMLParser()
    try:
        parser.feed(value)
        parser.close()
    except (TypeError, ValueError):
        raise ArticleExplanationSelectionError("选区内容无法读取。") from None
    return "".join(parser.parts)


def _selection_limit(value: object) -> int:
    if value is None:
        return DEFAULT_SELECTION_LIMIT
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArticleExplanationSelectionError(
            "选区长度配置无效。",
            code="discovery.article_explanation_settings_invalid.v1",
        )
    if not 1 <= value <= MAX_SELECTION_LIMIT:
        raise ArticleExplanationSelectionError(
            "选区长度配置超出允许范围。",
            code="discovery.article_explanation_settings_invalid.v1",
        )
    return value


def clean_article_selection(
    selection: str,
    *,
    max_chars: int | None = DEFAULT_SELECTION_LIMIT,
    source: Literal["html", "text"] = "html",
) -> CleanArticleSelection:
    value = _validate_text(selection, label="选区")
    if source not in {"html", "text"}:
        raise ValueError("source must be html or text")
    limit = _selection_limit(max_chars)
    text = _normalize_text(_source_text(value, source=source))
    if not text:
        raise ArticleExplanationSelectionError("选区没有可解释的文字。")
    original_char_count = len(text)
    processed = text[:limit]
    return CleanArticleSelection(
        text=processed,
        original_char_count=original_char_count,
        processed_char_count=len(processed),
        was_truncated=original_char_count > limit,
    )


def _canonical_heading(candidate: object, headings) -> str:
    if candidate is None:
        return ""
    value = _normalize_text(_validate_text(candidate, label="一级标题"))
    if not value:
        return ""
    normalized = {
        _normalize_text(item.label): item.label
        for item in headings
        if isinstance(getattr(item, "label", None), str)
    }
    return normalized.get(value, "")


def prepare_article_explanation_context(
    *,
    actor_id,
    article_id: str,
    selected_html: str | None = None,
    selected_text: str | None = None,
    section_heading: str | None = None,
    max_chars: int | None = None,
) -> ArticleExplanationContext:
    if actor_id is None or not is_active_account(actor_id):
        raise ArticleExplanationSelectionError(
            "登录后才能使用文章划词解释。",
            code="discovery.article_explanation_login_required.v1",
        )
    if selected_html is None and selected_text is None:
        raise ArticleExplanationSelectionError("请先选择要解释的文字。")
    if max_chars is None:
        try:
            from apps.navigation.queries.article_explanation import (
                ArticleExplanationSettingsQueryError,
                article_explanation_settings,
            )

            limit = _selection_limit(article_explanation_settings().selection_limit)
        except ArticleExplanationSettingsQueryError:
            raise ArticleExplanationSelectionError(
                "文章解释配置暂时不可用。",
                code="discovery.article_explanation_configuration_unavailable.v1",
            ) from None
    else:
        limit = _selection_limit(max_chars)
    try:
        page = article_detail_page(actor_id=actor_id, article_id=article_id)
    except (ArticleLoginRequired, ArticleNotFound):
        raise ArticleExplanationSelectionError(
            "只有公开文章可以使用划词解释。",
            code="discovery.article_explanation_article_unavailable.v1",
        ) from None
    if page.visibility != "PUBLIC":
        raise ArticleExplanationSelectionError(
            "只有公开文章可以使用划词解释。",
            code="discovery.article_explanation_article_unavailable.v1",
        )
    if selected_html is not None:
        selection = clean_article_selection(
            selected_html,
            max_chars=limit,
            source="html",
        )
    else:
        selection = clean_article_selection(
            selected_text or "",
            max_chars=limit,
            source="text",
        )
    try:
        metadata = visible_articles_by_ids(
            actor_id=None,
            article_ids=(page.article_id,),
        )
    except (TypeError, ValueError):
        metadata = ()
    if len(metadata) != 1:
        raise ArticleExplanationSelectionError(
            "文章当前不可用于划词解释。",
            code="discovery.article_explanation_article_unavailable.v1",
        )
    item = metadata[0]
    return ArticleExplanationContext(
        article_id=page.article_id,
        article_title=page.title,
        article_summary=getattr(item, "summary", None) or "",
        article_tags=tuple(tag.name for tag in page.tags if tag.name),
        section_heading=_canonical_heading(section_heading, page.toc),
        selected_text=selection.text,
        original_char_count=selection.original_char_count,
        processed_char_count=selection.processed_char_count,
        was_truncated=selection.was_truncated,
    )


__all__ = [
    "ArticleExplanationContext",
    "ArticleExplanationSelectionError",
    "CleanArticleSelection",
    "clean_article_selection",
    "prepare_article_explanation_context",
]
