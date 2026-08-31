from __future__ import annotations

from dataclasses import replace

from markdown_it import MarkdownIt

from .embeds import TrustedEmbedPolicy
from .html_policy import RenderedContent, sanitize_candidate_html, validate_source_text
from .latex import render_latex_block


def _line_content(state, line: int) -> str:
    start = state.bMarks[line] + state.tShift[line]
    return state.src[start : state.eMarks[line]].strip()


def _latex_block_rule(state, start_line: int, end_line: int, silent: bool) -> bool:
    if state.is_code_block(start_line) or _line_content(state, start_line) != "$$":
        return False

    closing_line = start_line + 1
    while closing_line < end_line:
        if _line_content(state, closing_line) == "$$":
            break
        closing_line += 1
    if closing_line >= end_line:
        return False
    if silent:
        return True

    token = state.push("kaj_latex_block", "div", 0)
    token.block = True
    token.map = [start_line, closing_line + 1]
    token.content = state.getLines(start_line + 1, closing_line, state.blkIndent, False)
    state.line = closing_line + 1
    return True


_MARKDOWN = MarkdownIt(
    "commonmark",
    {
        "html": True,
        "linkify": False,
        "typographer": False,
    },
).enable("table")
_MARKDOWN.block.ruler.before("fence", "kaj_latex_block", _latex_block_rule)
_MARKDOWN.add_render_rule(
    "kaj_latex_block",
    lambda renderer, tokens, index, options, env: render_latex_block(
        tokens[index].content
    ),
)


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
