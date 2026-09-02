import pytest

from apps.media.rendering import (
    MAX_LATEX_SOURCE_BYTES,
    TipTapSchemaError,
    normalize_tiptap_document,
    render_markdown,
    render_tiptap,
)


def test_markdown_supports_only_standalone_latex_blocks() -> None:
    rendered = render_markdown(
        "前文\n\n$$\n\\frac{1}{2}\n$$\n\n"
        "```text\n$$\nnot-formula\n$$\n```\n\n"
        "$$ inline $$"
    )

    assert rendered.html.count('data-kaj-latex="true"') == 1
    assert 'data-kaj-latex-source="\\frac{1}{2}"' in rendered.html
    assert "$$\nnot-formula\n$$" in rendered.html
    assert "$$ inline $$" in rendered.html
    assert rendered.block_start_lines == (0, 2, 6, 12)


def test_invalid_markdown_formula_is_kept_as_escaped_source() -> None:
    rendered = render_markdown("$$\n\\unknowncommand{<raw>}\n$$")

    assert "\\unknowncommand{&lt;raw&gt;}" in rendered.html
    assert 'data-kaj-latex="true"' in rendered.html


def test_tiptap_latex_block_is_v2_only_and_keeps_invalid_formula() -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "latexBlock",
                "attrs": {"formula": "\\unknowncommand{value}"},
            }
        ],
    }

    normalized = normalize_tiptap_document(document, schema_version=2)
    assert normalized.document == document
    assert 'data-kaj-latex="true"' in render_tiptap(document, schema_version=2).html
    with pytest.raises(TipTapSchemaError) as captured:
        normalize_tiptap_document(document, schema_version=1)
    assert captured.value.code == "media.tiptap.node_unsupported.v1"


def test_tiptap_latex_formula_has_a_bounded_source() -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "latexBlock",
                "attrs": {"formula": "x" * (MAX_LATEX_SOURCE_BYTES + 1)},
            }
        ],
    }

    with pytest.raises(TipTapSchemaError) as captured:
        normalize_tiptap_document(document, schema_version=2)
    assert captured.value.code == "media.tiptap.attributes_invalid.v1"
