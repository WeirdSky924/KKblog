from types import SimpleNamespace

from apps.authoring.presenters import version_preview
from apps.authoring.presenters.block_changes import block_change_presentation
from apps.content.block_changes import BlockChangeSummary
from apps.content.public import ArticleSnapshot, ContentFormat


def test_block_change_presentation_uses_counts_without_body_metadata() -> None:
    source = BlockChangeSummary(
        available=True,
        before_blocks=12,
        after_blocks=13,
        added_blocks=2,
        deleted_blocks=1,
        moved_blocks=3,
        type_changed_blocks=1,
        content_changed_blocks=4,
    )

    presentation = block_change_presentation(source)

    assert presentation.available is True
    assert presentation.before_blocks == 12
    assert presentation.after_blocks == 13
    assert presentation.labels == (
        "新增 2 个块",
        "删除 1 个块",
        "移动 3 个块",
        "1 个块类型变化",
        "修改 4 个块",
    )
    assert "body" not in repr(presentation).lower()


def test_unavailable_and_unchanged_presentations_are_explicit() -> None:
    unavailable = block_change_presentation(
        BlockChangeSummary(False, 0, 0, 0, 0, 0, 0, 0)
    )
    unchanged = block_change_presentation(BlockChangeSummary(True, 3, 3, 0, 0, 0, 0, 0))

    assert unavailable.available is False
    assert unavailable.labels == ()
    assert unchanged.available is True
    assert unchanged.labels == ()


def test_version_preview_projects_selected_revision_against_current(
    monkeypatch,
) -> None:
    paragraph = {
        "type": "paragraph",
        "content": [{"type": "text", "text": "private-body"}],
    }
    heading = {
        "type": "heading",
        "attrs": {
            "level": 2,
            "anchor": "kaj-h-33333333-3333-4333-8333-333333333333",
        },
        "content": paragraph["content"],
    }
    current = ArticleSnapshot(
        content_format=ContentFormat.TIPTAP_JSON,
        title="当前版本",
        body={"type": "doc", "content": [paragraph, {"type": "horizontalRule"}]},
        tiptap_schema_version=2,
    )
    source = ArticleSnapshot(
        content_format=ContentFormat.TIPTAP_JSON,
        title="所选版本",
        body={"type": "doc", "content": [{"type": "horizontalRule"}, heading]},
        tiptap_schema_version=2,
    )
    preview = SimpleNamespace(
        source_revision_id="source",
        row_version=2,
        token="restore-token",
        source=source,
        current=current,
        source_section_name="分区",
        source_tag_names=(),
        changed_fields=("body",),
    )
    monkeypatch.setattr(
        "apps.authoring.presenters.versions.preview_article_body",
        lambda **_kwargs: SimpleNamespace(html="<p>safe</p>"),
    )

    presented = version_preview(preview, can_restore=True)

    assert presented.block_changes.labels == (
        "移动 1 个块",
        "1 个块类型变化",
    )
    assert "private-body" not in repr(presented.block_changes)
