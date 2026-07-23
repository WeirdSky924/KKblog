from __future__ import annotations

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
)


def render_markdown(
    source: str,
    *,
    embed_policy: TrustedEmbedPolicy | None = None,
    allowed_media_ids: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RenderedContent:
    validate_source_text(source)
    candidate = _MARKDOWN.render(source)
    return sanitize_candidate_html(
        candidate,
        source=source,
        content_format="markdown",
        embed_policy=embed_policy,
        allowed_media_ids=allowed_media_ids,
    )
