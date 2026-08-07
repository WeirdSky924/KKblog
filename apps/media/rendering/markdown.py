from __future__ import annotations

from dataclasses import replace

from markdown_it import MarkdownIt

from .embeds import TrustedEmbedPolicy
from .html_policy import RenderedContent, sanitize_candidate_html, validate_source_text

_MARKDOWN = MarkdownIt(
    "commonmark",
    {
        "html": True,
        "linkify": False,
        "typographer": False,
    },
).enable("table")


def render_markdown(
    source: str,
    *,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RenderedContent:
    validate_source_text(source)
    tokens = _MARKDOWN.parse(source)
    candidate = _MARKDOWN.renderer.render(tokens, _MARKDOWN.options, {})
    rendered = sanitize_candidate_html(
        candidate,
        source=source,
        content_format="markdown",
        embed_policy=embed_policy,
        allowed_media_ids=allowed_media_ids,
    )
    block_start_lines = tuple(
        token.map[0]
        for token in tokens
        if token.level == 0 and token.nesting >= 0 and token.map is not None
    )
    return replace(rendered, block_start_lines=block_start_lines)
