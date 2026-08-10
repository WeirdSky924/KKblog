from dataclasses import asdict

from apps.content.block_changes import project_article_block_changes
from apps.core.ids import new_ulid


def _paragraph(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def _document(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


def _changes(before: dict, after: dict):
    return project_article_block_changes(
        before_content_format="TIPTAP_JSON",
        before_body=before,
        before_schema_version=2,
        after_content_format="TIPTAP_JSON",
        after_body=after,
        after_schema_version=2,
    )


def test_block_changes_classify_add_delete_move_and_type_without_text() -> None:
    media_id = new_ulid()
    image = {"type": "image", "attrs": {"src": f"media:{media_id}"}}
    before = _document(
        _paragraph("alpha-secret"),
        _paragraph("beta-secret"),
        image,
        _paragraph("deleted-secret"),
    )
    after = _document(
        _paragraph("beta-secret"),
        {
            "type": "heading",
            "attrs": {
                "level": 2,
                "anchor": "kaj-h-11111111-1111-4111-8111-111111111111",
            },
            "content": [{"type": "text", "text": "alpha-secret"}],
        },
        image,
        {"type": "horizontalRule"},
    )

    summary = _changes(before, after)

    assert asdict(summary) == {
        "available": True,
        "before_blocks": 4,
        "after_blocks": 4,
        "added_blocks": 1,
        "deleted_blocks": 1,
        "moved_blocks": 1,
        "type_changed_blocks": 1,
        "content_changed_blocks": 0,
    }
    exposed = repr(summary) + repr(asdict(summary))
    assert "secret" not in exposed
    assert media_id not in exposed


def test_repeated_blocks_have_deterministic_occurrence_matching() -> None:
    repeated = _paragraph("same-private-text")
    before = _document(repeated, repeated, _paragraph("tail-private-text"))
    after = _document(repeated, _paragraph("tail-private-text"), repeated)

    first = _changes(before, after)
    second = _changes(before, after)

    assert first == second
    assert first.added_blocks == 0
    assert first.deleted_blocks == 0
    assert first.moved_blocks == 1
    assert first.type_changed_blocks == 0
    assert first.content_changed_blocks == 0
    assert "private" not in repr(first)


def test_content_and_media_replacement_are_counts_only() -> None:
    before_media_id = new_ulid()
    after_media_id = new_ulid()
    before = _document(
        _paragraph("before-private-body"),
        {"type": "image", "attrs": {"src": f"media:{before_media_id}"}},
    )
    after = _document(
        _paragraph("after-private-body"),
        {"type": "image", "attrs": {"src": f"media:{after_media_id}"}},
    )

    summary = _changes(before, after)

    assert summary.content_changed_blocks == 2
    assert summary.added_blocks == 0
    assert summary.deleted_blocks == 0
    exposed = repr(summary)
    assert "private" not in exposed
    assert before_media_id not in exposed
    assert after_media_id not in exposed


def test_non_tiptap_comparison_is_explicitly_unavailable() -> None:
    summary = project_article_block_changes(
        before_content_format="MARKDOWN",
        before_body="private markdown",
        before_schema_version=None,
        after_content_format="TIPTAP_JSON",
        after_body=_document(_paragraph("private rich text")),
        after_schema_version=2,
    )

    assert summary.available is False
    assert summary.before_blocks == 0
    assert summary.after_blocks == 0
    assert "private" not in repr(summary)


def test_large_repeated_document_uses_bounded_deterministic_matching() -> None:
    blocks = [_paragraph(f"private-{index}") for index in range(4_000)]
    before = _document(*blocks)
    after = _document(*blocks[1:], blocks[0])

    summary = _changes(before, after)

    assert summary.before_blocks == 4_000
    assert summary.after_blocks == 4_000
    assert summary.added_blocks == 0
    assert summary.deleted_blocks == 0
    assert summary.type_changed_blocks == 0
    assert summary.content_changed_blocks == 0
    assert summary.moved_blocks == 1
