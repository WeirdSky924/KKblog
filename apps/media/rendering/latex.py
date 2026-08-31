from __future__ import annotations

import re
from html import escape
from unicodedata import category

MAX_LATEX_SOURCE_BYTES = 16 * 1024
MAX_LATEX_BLOCKS = 200

# Definitions are intentionally rejected by the browser renderer.  Built-in
# KaTeX commands remain available, but a document cannot change the command
# vocabulary used by another document or by a later render.
DISALLOWED_LATEX_MACRO_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|def|gdef|xdef|edef|let|"
    r"DeclareMathOperator|newenvironment|renewenvironment)\b",
    re.IGNORECASE,
)


def normalize_latex_source(source: object) -> str:
    if not isinstance(source, str):
        raise ValueError("LaTeX source must be text")
    try:
        encoded = source.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("LaTeX source is invalid") from exc
    if len(encoded) > MAX_LATEX_SOURCE_BYTES:
        raise ValueError("LaTeX source exceeds the configured limit")
    if any(
        category(character) == "Cc" and character not in "\t\n\r"
        for character in source
    ):
        raise ValueError("LaTeX source contains control characters")
    return source.strip()


def contains_disallowed_latex_macro(source: str) -> bool:
    return bool(DISALLOWED_LATEX_MACRO_RE.search(source))


def latex_fallback_source(source: object) -> str:
    normalized = normalize_latex_source(source)
    return f"$$\n{normalized}\n$$"


def render_latex_block(source: object) -> str:
    normalized = normalize_latex_source(source)
    fallback = latex_fallback_source(normalized)
    return (
        '<div data-kaj-latex="true" '
        f'data-kaj-latex-source="{escape(normalized, quote=True)}">'
        f"{escape(fallback, quote=False)}</div>"
    )


__all__ = [
    "DISALLOWED_LATEX_MACRO_RE",
    "MAX_LATEX_BLOCKS",
    "MAX_LATEX_SOURCE_BYTES",
    "contains_disallowed_latex_macro",
    "latex_fallback_source",
    "normalize_latex_source",
    "render_latex_block",
]
