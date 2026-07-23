from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from markdown_it import MarkdownIt

from apps.core.ids import normalize_ulid

from .html_policy import RenderingError, validate_source_text

_MARKDOWN = MarkdownIt("commonmark", {"html": True})
_MAX_TIPTAP_NODES = 10_000


def _normalize_source(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith("media:"):
        return None
    try:
        return normalize_ulid(value.removeprefix("media:"))
    except (TypeError, ValueError):
        raise RenderingError("Invalid media reference") from None


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def markdown_media_ids(source: str) -> tuple[str, ...]:
    validate_source_text(source)
    references: list[str] = []
    for token in _MARKDOWN.parse(source):
        candidates = token.children or (token,)
        for candidate in candidates:
            if candidate.type != "image":
                continue
            normalized = _normalize_source(candidate.attrGet("src"))
            if normalized is not None:
                references.append(normalized)
    return _ordered_unique(references)


def tiptap_media_ids(document: dict[str, Any]) -> tuple[str, ...]:
    if not isinstance(document, dict):
        raise RenderingError("TipTap document root must be an object")
    references: list[str] = []
    stack: list[object] = [document]
    visited = 0
    while stack:
        node = stack.pop()
        visited += 1
        if visited > _MAX_TIPTAP_NODES:
            raise RenderingError("TipTap document exceeds structural limits")
        if not isinstance(node, dict):
            continue
        if node.get("type") == "image":
            attrs = node.get("attrs")
            if isinstance(attrs, dict):
                normalized = _normalize_source(attrs.get("src"))
                if normalized is not None:
                    references.append(normalized)
        content = node.get("content", ())
        if isinstance(content, list):
            stack.extend(reversed(content))
    return _ordered_unique(references)
