from pathlib import Path

import pytest

from apps.content.rendering import (
    ArticleRenderingMode,
    normalize_article_tiptap_body,
    render_article_body,
)
from apps.core.ids import new_ulid
from apps.media.public import RenderingError, TrustedEmbedPolicy


def _resource_document(*, media_id: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "before"}],
            },
            {"type": "image", "attrs": {"src": f"media:{media_id}"}},
            {
                "type": "attachment",
                "attrs": {"src": f"media:{media_id}"},
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "after"}],
            },
        ],
    }


def test_rendering_modes_own_resource_degradation_semantics(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.content.rendering_policy._provider",
        lambda: TrustedEmbedPolicy(),
    )
    media_id = new_ulid()
    document = _resource_document(media_id=media_id)

    with pytest.raises(RenderingError):
        render_article_body(
            content_format="TIPTAP_JSON",
            body=document,
            tiptap_schema_version=2,
            mode=ArticleRenderingMode.STRICT,
        )

    reader = render_article_body(
        content_format="TIPTAP_JSON",
        body=document,
        tiptap_schema_version=2,
        mode=ArticleRenderingMode.READER,
    )
    assert "图片不可用" in reader.html
    assert "附件不可用" in reader.html
    assert reader.plain_text == "before 图片不可用 附件不可用 after"

    for mode in (ArticleRenderingMode.SUMMARY, ArticleRenderingMode.EXPORT):
        projection = render_article_body(
            content_format="TIPTAP_JSON",
            body=document,
            tiptap_schema_version=2,
            mode=mode,
        )
        assert projection.html == "<p>before</p><p>after</p>"
        assert projection.plain_text == "before after"
        assert projection.readable_markdown == (
            "before\n\nafter" if mode is ArticleRenderingMode.EXPORT else ""
        )


def test_only_content_projection_calls_media_body_renderers() -> None:
    root = Path(__file__).resolve().parents[3]
    direct_callers = []
    for path in (root / "apps" / "content").rglob("*.py"):
        if path.name == "rendering.py" or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "render_markdown(" in source or "render_tiptap(" in source:
            direct_callers.append(str(path.relative_to(root)))
    assert direct_callers == []


def test_content_projection_records_safe_render_dimensions(monkeypatch) -> None:
    metrics = []
    monkeypatch.setattr(
        "apps.content.rendering_policy._provider",
        lambda: TrustedEmbedPolicy(),
    )
    monkeypatch.setattr(
        "apps.content.rendering.record_rich_text_render_metric",
        lambda **values: metrics.append(values),
    )
    private_text = "正文不得进入性能指标"

    projection = render_article_body(
        content_format="TIPTAP_JSON",
        body={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": private_text}],
                }
            ],
        },
        tiptap_schema_version=2,
        mode=ArticleRenderingMode.STRICT,
    )

    assert private_text in projection.html
    assert len(metrics) == 1
    assert metrics[0]["content_format"] == "TIPTAP_JSON"
    assert metrics[0]["mode"] == "strict"
    assert metrics[0]["schema_version"] == 2
    assert metrics[0]["node_count"] == 3
    assert metrics[0]["max_depth"] == 2
    assert metrics[0]["table_cells"] == 0
    assert metrics[0]["outcome"] == "success"
    assert private_text not in repr(metrics[0])


def test_content_projection_records_rejection_without_source(monkeypatch) -> None:
    metrics = []
    monkeypatch.setattr(
        "apps.content.rendering_policy._provider",
        lambda: TrustedEmbedPolicy(),
    )
    monkeypatch.setattr(
        "apps.content.rendering.record_rich_text_render_metric",
        lambda **values: metrics.append(values),
    )
    private_text = "不可写入日志的正文"

    with pytest.raises(RenderingError):
        render_article_body(
            content_format="TIPTAP_JSON",
            body={
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": private_text,
                                "marks": [
                                    {
                                        "type": "link",
                                        "attrs": {"href": "javascript:private"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            tiptap_schema_version=2,
            mode=ArticleRenderingMode.STRICT,
        )

    assert len(metrics) == 1
    assert metrics[0]["outcome"] == "rejected"
    assert metrics[0]["error_code"] == "media.tiptap.link_invalid.v1"
    assert metrics[0]["node_count"] == 0
    assert private_text not in repr(metrics[0])


def test_content_normalization_records_structural_rejection(monkeypatch) -> None:
    metrics = []
    monkeypatch.setattr(
        "apps.content.rendering.record_rich_text_render_metric",
        lambda **values: metrics.append(values),
    )
    nested = {"type": "paragraph", "content": []}
    for _ in range(102):
        nested = {"type": "blockquote", "content": [nested]}

    with pytest.raises(RenderingError):
        normalize_article_tiptap_body(
            {"type": "doc", "content": [nested]},
            schema_version=2,
            mode=ArticleRenderingMode.STRICT,
        )

    assert metrics == [
        {
            "content_format": "TIPTAP_JSON",
            "mode": "strict",
            "schema_version": 2,
            "source_bytes": 0,
            "node_count": 0,
            "max_depth": 0,
            "table_cells": 0,
            "duration_ms": metrics[0]["duration_ms"],
            "outcome": "rejected",
            "error_code": "media.tiptap.structure_limit.v1",
        }
    ]
