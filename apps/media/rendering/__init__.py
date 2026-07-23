from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from .embeds import TrustedEmbedPolicy
from .html_policy import (
    SANITIZER_VERSION,
    RenderedContent,
    RenderingError,
    render_author_html,
    render_cache_key,
)
from .markdown import render_markdown
from .references import markdown_media_ids, tiptap_media_ids
from .tiptap import render_tiptap


class ContentFormat(StrEnum):
    MARKDOWN = "markdown"
    TIPTAP = "tiptap"
    HTML = "html"


def render_import_preview(
    source: str | dict[str, Any],
    content_format: ContentFormat | str,
    *,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RenderedContent:
    try:
        normalized_format = ContentFormat(content_format)
    except ValueError as exc:
        raise RenderingError("Unsupported import content format") from exc
    options = {
        "embed_policy": embed_policy,
        "allowed_media_ids": allowed_media_ids,
    }
    if normalized_format is ContentFormat.MARKDOWN:
        if not isinstance(source, str):
            raise RenderingError("Markdown import source must be text")
        return render_markdown(source, **options)
    if normalized_format is ContentFormat.HTML:
        if not isinstance(source, str):
            raise RenderingError("HTML import source must be text")
        return render_author_html(source, **options)
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError as exc:
            raise RenderingError("TipTap import source must be valid JSON") from exc
    if not isinstance(source, dict):
        raise RenderingError("TipTap import source must be an object")
    return render_tiptap(source, **options)


__all__ = [
    "ContentFormat",
    "RenderedContent",
    "RenderingError",
    "SANITIZER_VERSION",
    "TrustedEmbedPolicy",
    "render_author_html",
    "render_cache_key",
    "render_import_preview",
    "render_markdown",
    "render_tiptap",
    "markdown_media_ids",
    "tiptap_media_ids",
]
