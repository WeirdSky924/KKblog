from copy import deepcopy

import pytest

from apps.core.ids import new_ulid
from apps.media.rendering import (
    TipTapAttachmentMetadata,
    TipTapSchemaError,
    normalize_tiptap_document,
    project_tiptap_outline,
    render_tiptap,
)
from apps.media.rendering.html_policy import MAX_SOURCE_BYTES
from apps.media.rendering.tiptap_schema import (
    MAX_TIPTAP_DEPTH,
    MAX_TIPTAP_NODES,
    MAX_TIPTAP_TABLE_COLUMNS,
    MAX_TIPTAP_TABLE_ROWS,
)


def _linked_document(href: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "link",
                        "marks": [{"type": "link", "attrs": {"href": href}}],
                    }
                ],
            }
        ],
    }


def _error(document: object, *, version: object = 2) -> TipTapSchemaError:
    with pytest.raises(TipTapSchemaError) as captured:
        normalize_tiptap_document(document, schema_version=version)  # type: ignore[arg-type]
    return captured.value


def _table_document(
    rows: int,
    columns: int,
    *,
    header: bool = True,
) -> dict:
    return {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": (
                                    "tableHeader"
                                    if header and row_index == 0
                                    else "tableCell"
                                ),
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": f"{row_index}:{column_index}",
                                            }
                                        ],
                                    }
                                ],
                            }
                            for column_index in range(columns)
                        ],
                    }
                    for row_index in range(rows)
                ],
            }
        ],
    }


@pytest.mark.parametrize("version", [None, True, 0, 3, "2"])
def test_unknown_schema_versions_fail_closed(version: object) -> None:
    error = _error({"type": "doc", "content": []}, version=version)
    assert error.code == "media.tiptap.version_invalid.v1"


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ([], "media.tiptap.root_invalid.v1"),
        (
            {"type": "doc", "content": [{"type": "unknown-user-node"}]},
            "media.tiptap.node_unsupported.v1",
        ),
        (
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "attrs": {"style": "position:fixed"},
                    }
                ],
            },
            "media.tiptap.attributes_invalid.v1",
        ),
        (
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "duplicate",
                                "marks": [
                                    {"type": "bold"},
                                    {"type": "bold"},
                                ],
                            }
                        ],
                    }
                ],
            },
            "media.tiptap.mark_invalid.v1",
        ),
        (
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "unknown mark",
                                "marks": [{"type": "highlight"}],
                            }
                        ],
                    }
                ],
            },
            "media.tiptap.mark_invalid.v1",
        ),
        (
            {
                "type": "doc",
                "content": [
                    {
                        "type": "image",
                        "attrs": {"src": "https://example.test/image.png"},
                    }
                ],
            },
            "media.tiptap.media_invalid.v1",
        ),
        (
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "\ud800"}],
                    }
                ],
            },
            "media.tiptap.text_invalid.v1",
        ),
    ],
)
def test_invalid_nodes_marks_attributes_and_media_have_stable_codes(
    document: object,
    code: str,
) -> None:
    error = _error(document)
    assert error.code == code
    assert "unknown-user-node" not in str(error)


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "//evil.test/path",
        "https://user:pass@example.test/private",
        "https://example.test:444/path",
        "https://example.test/control\x00",
        "https://example.test/control\x7f",
    ],
)
def test_v2_links_reject_dangerous_schemes_credentials_ports_and_controls(
    href: str,
) -> None:
    error = _error(_linked_document(href))
    assert error.code == "media.tiptap.link_invalid.v1"
    assert href not in str(error)


def test_legacy_links_and_code_languages_degrade_without_rewriting_source() -> None:
    source = _linked_document("javascript:alert(1)")
    source["content"].append(
        {
            "type": "codeBlock",
            "attrs": {"language": "legacy-unknown"},
            "content": [{"type": "text", "text": "<script>x</script>"}],
        }
    )
    original = deepcopy(source)

    rendered = render_tiptap(source, schema_version=1).html

    assert source == original
    assert (
        rendered
        == "<p><a>link</a></p><pre><code>&lt;script&gt;x&lt;/script&gt;</code></pre>"
    )
    assert "javascript:" not in rendered


def test_structure_and_serialized_source_limits_have_distinct_codes() -> None:
    nested: dict = {"type": "paragraph", "content": []}
    for _ in range(MAX_TIPTAP_DEPTH + 1):
        nested = {"type": "blockquote", "content": [nested]}
    structural = _error({"type": "doc", "content": [nested]})
    assert structural.code == "media.tiptap.structure_limit.v1"

    oversized = _error(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "x" * MAX_SOURCE_BYTES}],
                }
            ],
        }
    )
    assert oversized.code == "media.tiptap.source_limit.v1"


def test_node_count_accepts_the_exact_boundary_and_rejects_one_more() -> None:
    text_paragraphs = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "x"}],
        }
        for _ in range((MAX_TIPTAP_NODES - 2) // 2)
    ]
    exact = {
        "type": "doc",
        "content": [*text_paragraphs, {"type": "paragraph", "content": []}],
    }

    normalized = normalize_tiptap_document(exact, schema_version=2)
    assert normalized.node_count == MAX_TIPTAP_NODES

    exceeded = deepcopy(exact)
    exceeded["content"].append({"type": "paragraph", "content": []})
    error = _error(exceeded)
    assert error.code == "media.tiptap.structure_limit.v1"


def test_pre_normalized_document_is_not_validated_twice(monkeypatch) -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "render once"}],
            }
        ],
    }
    normalized = normalize_tiptap_document(document, schema_version=2)
    monkeypatch.setattr(
        "apps.media.rendering.tiptap.normalize_tiptap_document",
        lambda *args, **kwargs: pytest.fail("normalized document was validated twice"),
    )

    rendered = render_tiptap(normalized, schema_version=2)
    assert rendered.html == "<p>render once</p>"
    assert rendered.node_count == 3


def test_rendering_escapes_xss_and_requires_explicit_media_capabilities() -> None:
    media_id = new_ulid()
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "<script>alert(1)</script>",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {"href": "https://example.com/read"},
                            },
                            {"type": "bold"},
                        ],
                    }
                ],
            },
            {
                "type": "image",
                "attrs": {
                    "src": f"media:{media_id}",
                    "alt": 'image" onerror="alert(1)',
                    "width": 50,
                },
            },
        ],
    }

    with pytest.raises(TipTapSchemaError) as denied:
        render_tiptap(document, schema_version=2)
    assert denied.value.code == "media.tiptap.media_invalid.v1"

    rendered = render_tiptap(
        document,
        schema_version=2,
        allowed_media_ids={media_id},
    ).html
    assert "<script" not in rendered
    assert ' onerror="' not in rendered
    assert f'src="/_kaj/media/{media_id}"' in rendered
    assert 'data-width="50"' in rendered
    assert 'rel="noopener noreferrer"' in rendered
    assert 'target="_blank"' in rendered


def test_v2_structural_blocks_share_renderer_and_sanitizer_contract() -> None:
    attachment_id = new_ulid()
    document = {
        "type": "doc",
        "content": [
            {
                "type": "taskList",
                "content": [
                    {
                        "type": "taskItem",
                        "attrs": {"checked": True},
                        "content": [{"type": "paragraph", "content": []}],
                    }
                ],
            },
            {
                "type": "callout",
                "attrs": {"kind": "warning"},
                "content": [{"type": "paragraph", "content": []}],
            },
            {
                "type": "attachment",
                "attrs": {"src": f"media:{attachment_id}"},
            },
            {
                "type": "embed",
                "attrs": {
                    "source": "bilibili",
                    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                },
            },
        ],
    }

    rendered = render_tiptap(
        document,
        schema_version=2,
        allowed_attachment_id=attachment_id,
    ).html
    assert 'data-task-list="true"' in rendered
    assert 'data-task-checked="true"' in rendered
    assert 'data-callout="warning"' in rendered
    assert f'href="/_kaj/media/{attachment_id}"' in rendered
    assert "<iframe" in rendered


def test_heading_anchors_are_safe_stable_and_projected_from_json() -> None:
    anchor = "kaj-h-00000000-0000-4000-8000-000000000001"
    document = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2, "anchor": anchor},
                "content": [{"type": "text", "text": "重复 标题"}],
            },
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "重复 标题"}],
            },
            {"type": "heading", "attrs": {"level": 6}, "content": []},
        ],
    }

    normalized = normalize_tiptap_document(document, schema_version=2)
    assert normalized.document["content"][0]["attrs"]["anchor"] == anchor
    outline = project_tiptap_outline(document, schema_version=2)
    assert [(item.level, item.text) for item in outline] == [
        (2, "重复 标题"),
        (3, "重复 标题"),
        (6, ""),
    ]
    assert outline[0].anchor == anchor
    assert len({item.anchor for item in outline}) == 3
    assert all(item.anchor.startswith("kaj-h-") for item in outline)

    first = render_tiptap(document, schema_version=2).html
    second = render_tiptap(document, schema_version=2).html
    assert first == second
    assert f'<h2 id="{anchor}">' in first
    assert all(f'id="{item.anchor}"' in first for item in outline)

    invalid = deepcopy(document)
    invalid["content"][0]["attrs"]["anchor"] = 'unsafe" onclick="alert(1)'
    error = _error(invalid)
    assert error.code == "media.tiptap.attributes_invalid.v1"

    legacy = deepcopy(document)
    legacy["content"][0]["attrs"].pop("anchor")
    assert all("anchor" not in item["attrs"] for item in legacy["content"])
    assert all(
        item.anchor.startswith("kaj-h-legacy-")
        for item in project_tiptap_outline(legacy, schema_version=1)
    )
    legacy["content"][0]["attrs"]["anchor"] = anchor
    assert _error(legacy, version=1).code == "media.tiptap.attributes_invalid.v1"


def test_attachment_card_uses_external_metadata_and_stays_unique() -> None:
    attachment_id = new_ulid()
    attachment = {
        "type": "attachment",
        "attrs": {"src": f"media:{attachment_id}"},
    }
    document = {"type": "doc", "content": [attachment]}
    rendered = render_tiptap(
        document,
        schema_version=2,
        allowed_attachment_id=attachment_id,
        attachment_metadata=TipTapAttachmentMetadata(
            asset_id=attachment_id,
            original_name='guide"<unsafe>.zip',
            detected_mime="application/zip",
            size_bytes=2_097_152,
        ),
    ).html

    assert 'data-kaj-attachment-card="true"' in rendered
    assert "guide&quot;&lt;unsafe&gt;.zip" in rendered
    assert "ZIP · 2.0 MiB" in rendered
    assert f'href="/_kaj/media/{attachment_id}"' in rendered
    assert " download=" in rendered
    assert "<unsafe>" not in rendered

    duplicate = _error({"type": "doc", "content": [attachment, attachment]})
    assert duplicate.code == "media.tiptap.attachment_invalid.v1"


def test_v2_basic_table_uses_the_shared_renderer_and_sanitizer() -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableHeader",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "名称"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableHeader",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "内容"}],
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Kaj"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "<script>"}
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }

    rendered = render_tiptap(document, schema_version=2).html
    assert rendered.startswith('<div data-table-scroll="true"><table>')
    assert "<table><thead><tr><th><p>名称</p></th>" in rendered
    assert "</thead><tbody><tr><td><p>Kaj</p></td>" in rendered
    assert rendered.endswith("</tbody></table></div>")
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_v2_table_accepts_the_exact_capacity_boundary_without_truncation() -> None:
    document = _table_document(
        MAX_TIPTAP_TABLE_ROWS,
        MAX_TIPTAP_TABLE_COLUMNS,
    )

    normalized = normalize_tiptap_document(document, schema_version=2).document
    table = normalized["content"][0]

    assert len(table["content"]) == MAX_TIPTAP_TABLE_ROWS
    assert {len(row["content"]) for row in table["content"]} == {
        MAX_TIPTAP_TABLE_COLUMNS
    }
    assert table["content"][0]["content"][0]["type"] == "tableHeader"
    assert (
        table["content"][-1]["content"][-1]["content"][0]["content"][0]["text"]
        == f"{MAX_TIPTAP_TABLE_ROWS - 1}:{MAX_TIPTAP_TABLE_COLUMNS - 1}"
    )


@pytest.mark.parametrize(
    "case",
    [
        "too-many-rows",
        "too-many-columns",
        "empty-table",
        "empty-row",
        "uneven-rows",
        "mixed-first-row",
        "header-in-body",
        "table-attrs",
        "cell-attrs",
        "wrong-row-node",
        "wrong-cell-node",
        "empty-cell",
        "direct-nested-table",
        "indirect-nested-table",
    ],
)
def test_v2_malformed_and_nested_tables_fail_closed_with_one_code(case: str) -> None:
    document = _table_document(2, 2)
    table = document["content"][0]
    if case == "too-many-rows":
        document = _table_document(MAX_TIPTAP_TABLE_ROWS + 1, 1)
    elif case == "too-many-columns":
        document = _table_document(1, MAX_TIPTAP_TABLE_COLUMNS + 1)
    elif case == "empty-table":
        table["content"] = []
    elif case == "empty-row":
        table["content"][0]["content"] = []
    elif case == "uneven-rows":
        table["content"][1]["content"].pop()
    elif case == "mixed-first-row":
        table["content"][0]["content"][1]["type"] = "tableCell"
    elif case == "header-in-body":
        table["content"][1]["content"][0]["type"] = "tableHeader"
    elif case == "table-attrs":
        table["attrs"] = {"layout": "fixed"}
    elif case == "cell-attrs":
        table["content"][0]["content"][0]["attrs"] = {
            "colspan": 2,
            "rowspan": 1,
            "colwidth": None,
        }
    elif case == "wrong-row-node":
        table["content"][0]["type"] = "paragraph"
    elif case == "wrong-cell-node":
        table["content"][0]["content"][0]["type"] = "paragraph"
    elif case == "empty-cell":
        table["content"][0]["content"][0]["content"] = []
    elif case == "direct-nested-table":
        table["content"][1]["content"][0]["content"] = [deepcopy(table)]
    elif case == "indirect-nested-table":
        table["content"][1]["content"][0]["content"] = [
            {
                "type": "callout",
                "attrs": {"kind": "info"},
                "content": [deepcopy(table)],
            }
        ]

    error = _error(document)

    assert error.code == "media.tiptap.table_invalid.v1"
    assert case not in str(error)


def test_v2_table_text_is_escaped_and_unsafe_links_keep_their_specific_code() -> None:
    document = _table_document(1, 1, header=False)
    paragraph = document["content"][0]["content"][0]["content"][0]["content"][0]
    paragraph["content"] = [
        {"type": "text", "text": '<img src=x onerror="alert(1)"><script>x</script>'}
    ]

    rendered = render_tiptap(document, schema_version=2).html

    assert "<script" not in rendered
    assert "<img" not in rendered
    assert "&lt;img src=x onerror=" in rendered

    paragraph["content"][0]["marks"] = [
        {"type": "link", "attrs": {"href": "javascript:alert(1)"}}
    ]
    error = _error(document)
    assert error.code == "media.tiptap.link_invalid.v1"


def test_v1_documents_remain_readable_but_do_not_gain_table_support() -> None:
    legacy = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "legacy remains readable"}],
            }
        ],
    }
    assert render_tiptap(legacy, schema_version=1).html == (
        "<p>legacy remains readable</p>"
    )

    error = _error(_table_document(1, 1), version=1)
    assert error.code == "media.tiptap.node_unsupported.v1"
