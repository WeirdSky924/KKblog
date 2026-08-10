from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from markdown_it import MarkdownIt

from apps.core.ids import normalize_ulid

from .html_policy import RenderingError, validate_source_text
from .tiptap_schema import (
    LEGACY_TIPTAP_SCHEMA_VERSION,
    normalize_tiptap_document,
)

_MARKDOWN = MarkdownIt("commonmark", {"html": True})


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


def tiptap_media_ids(
    document: dict[str, Any],
    *,
    schema_version: int = LEGACY_TIPTAP_SCHEMA_VERSION,
) -> tuple[str, ...]:
    return normalize_tiptap_document(
        document,
        schema_version=schema_version,
    ).body_media_ids


def tiptap_attachment_ids(
    document: dict[str, Any],
    *,
    schema_version: int = LEGACY_TIPTAP_SCHEMA_VERSION,
) -> tuple[str, ...]:
    return normalize_tiptap_document(
        document,
        schema_version=schema_version,
    ).attachment_media_ids
