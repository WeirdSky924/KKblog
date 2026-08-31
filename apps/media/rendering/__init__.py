from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from .embeds import (
    TrustedEmbedPolicy,
    configure_trusted_embed_policy_provider,
    configured_trusted_embed_policy,
)
from .html_policy import (
    SANITIZER_VERSION,
    RenderedContent,
    RenderingError,
    configured_rendering_version,
    render_author_html,
    render_cache_key,
)
from .latex import (
    MAX_LATEX_BLOCKS,
    MAX_LATEX_SOURCE_BYTES,
    contains_disallowed_latex_macro,
    latex_fallback_source,
    normalize_latex_source,
    render_latex_block,
)
from .markdown import render_markdown
from .references import markdown_media_ids, tiptap_attachment_ids, tiptap_media_ids
from .tiptap import (
    TIPTAP_RENDERER_VERSION,
    TipTapAttachmentMetadata,
    TipTapOutlineItem,
    project_tiptap_outline,
    render_tiptap,
)
from .tiptap_schema import (
    CURRENT_TIPTAP_SCHEMA_VERSION,
    LEGACY_TIPTAP_SCHEMA_VERSION,
    SUPPORTED_TIPTAP_SCHEMA_VERSIONS,
    TIPTAP_CODE_LANGUAGES,
    TIPTAP_SCHEMA_FINGERPRINT,
    NormalizedTipTapDocument,
    TipTapSchemaError,
    normalize_tiptap_document,
)


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
    return render_tiptap(
        source,
        schema_version=CURRENT_TIPTAP_SCHEMA_VERSION,
        **options,
    )


__all__ = [
    "ContentFormat",
    "CURRENT_TIPTAP_SCHEMA_VERSION",
    "LEGACY_TIPTAP_SCHEMA_VERSION",
    "NormalizedTipTapDocument",
    "RenderedContent",
    "RenderingError",
    "MAX_LATEX_BLOCKS",
    "MAX_LATEX_SOURCE_BYTES",
    "SANITIZER_VERSION",
    "SUPPORTED_TIPTAP_SCHEMA_VERSIONS",
    "TIPTAP_CODE_LANGUAGES",
    "TIPTAP_RENDERER_VERSION",
    "TipTapAttachmentMetadata",
    "TipTapOutlineItem",
    "TIPTAP_SCHEMA_FINGERPRINT",
    "TrustedEmbedPolicy",
    "TipTapSchemaError",
    "configure_trusted_embed_policy_provider",
    "configured_rendering_version",
    "configured_trusted_embed_policy",
    "render_author_html",
    "render_latex_block",
    "normalize_latex_source",
    "latex_fallback_source",
    "contains_disallowed_latex_macro",
    "render_cache_key",
    "render_import_preview",
    "render_markdown",
    "render_tiptap",
    "project_tiptap_outline",
    "markdown_media_ids",
    "normalize_tiptap_document",
    "tiptap_attachment_ids",
    "tiptap_media_ids",
]
