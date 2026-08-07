import re

import pytest

from apps.core.ids import new_ulid
from apps.media.rendering import (
    SANITIZER_VERSION,
    ContentFormat,
    RenderingError,
    TrustedEmbedPolicy,
    render_author_html,
    render_cache_key,
    render_import_preview,
    render_markdown,
    render_tiptap,
)
from apps.media.rendering.html_policy import MAX_SOURCE_BYTES


@pytest.mark.parametrize(
    "payload",
    [
        '<script>window.__kaj_xss = "script"</script><p>可读正文</p>',
        '<img src="x" onerror="window.__kaj_xss=1"><p>图片后正文</p>',
        '<svg><a xlink:href="javascript:alert(1)">svg</a></svg>',
        '<math><mi xlink:href="data:text/html,x">math</mi></math>',
        '<form id="location"><input name="cookie" formaction="https://evil.test"></form>',
        '<p id="__proto__" class="unsafe" style="position:fixed">属性正文</p>',
        '<a href="javascript:alert(1)" ping="https://evil.test">危险链接</a>',
        '<a href="data:text/html,<script>alert(1)</script>">data 链接</a>',
        '<iframe src="https://evil.test" srcdoc="<script>x</script>"></iframe>',
        '<object data="https://evil.test"></object><!-- secret comment -->',
    ],
)
def test_author_html_removes_active_content_attributes_and_clobbering(
    payload: str,
) -> None:
    rendered = render_author_html(payload)
    lowered = rendered.html.casefold()
    for forbidden in (
        "<script",
        "onerror",
        "javascript:",
        "data:text/html",
        "<iframe",
        "<object",
        "<svg",
        "<math",
        "<form",
        "<input",
        " id=",
        " name=",
        " style=",
        " formaction=",
        " ping=",
        "secret comment",
    ):
        assert forbidden not in lowered


def test_all_entry_points_share_versioned_sanitizer() -> None:
    markdown = render_markdown("## Markdown\n\n<strong onclick=alert(1)>正文</strong>")
    tiptap = render_tiptap(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "TipTap 正文"}],
                }
            ],
        }
    )
    author_html = render_author_html("<p onmouseover=alert(1)>HTML 正文</p>")
    imported = render_import_preview(
        "## 导入正文\n\n<script>alert(1)</script>",
        ContentFormat.MARKDOWN,
    )

    assert {
        item.sanitizer_version for item in (markdown, tiptap, author_html, imported)
    } == {SANITIZER_VERSION}
    assert "Markdown" in markdown.html and "onclick" not in markdown.html
    assert "TipTap 正文" in tiptap.html
    assert "HTML 正文" in author_html.html and "onmouseover" not in author_html.html
    assert "导入正文" in imported.html and "<script" not in imported.html
    assert render_cache_key("same", version="kaj-html-v1") != render_cache_key(
        "same", version="kaj-html-v2"
    )


def test_markdown_exposes_top_level_source_lines_for_editor_preview_sync() -> None:
    rendered = render_markdown(
        "# 标题\n\n"
        "第一段\n\n"
        "- 列表一\n"
        "- 列表二\n\n"
        "```text\n"
        "代码\n"
        "```\n\n"
        "| 列一 | 列二 |\n"
        "| --- | --- |\n"
        "| A | B |\n"
    )

    assert rendered.block_start_lines == (0, 2, 4, 7, 11)


def test_links_are_protocol_checked_and_only_external_links_open_new_tab() -> None:
    rendered = render_author_html(
        '<p><a href="https://example.com/read?q=1" target="self">外链</a> '
        '<a href="/articles/one?from=body">站内</a> '
        '<a href="mailto:reader@kaj.test">邮件</a> '
        '<a href="//evil.test/path">协议相对</a></p>'
    ).html
    assert re.search(
        r'<a href="https://example\.com/read\?q=1" rel="noopener noreferrer" target="_blank">外链</a>',
        rendered,
    )
    assert '<a href="/articles/one?from=body">站内</a>' in rendered
    assert '<a href="mailto:reader@kaj.test">邮件</a>' in rendered
    assert "//evil.test/path" not in rendered
    assert 'target="self"' not in rendered


def test_markdown_images_require_explicit_media_ids_and_allowlist() -> None:
    allowed = new_ulid()
    denied = new_ulid()
    rendered = render_markdown(
        f"![允许图片](media:{allowed})\n\n"
        f"![未绑定图片](media:{denied})\n\n"
        "![远程图片](https://evil.test/tracker.png)",
        allowed_media_ids={allowed},
    ).html
    assert f'src="/_kaj/media/{allowed}"' in rendered
    assert 'alt="允许图片"' in rendered
    assert denied not in rendered
    assert "evil.test" not in rendered
    assert rendered.count("<img") == 1


def test_tiptap_schema_is_bounded_and_rejects_unknown_active_nodes() -> None:
    valid = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [
                    {
                        "type": "text",
                        "text": "标题",
                        "marks": [{"type": "bold"}],
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "链接",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {"href": "https://example.com"},
                            }
                        ],
                    }
                ],
            },
        ],
    }
    rendered = render_tiptap(valid).html
    assert "<h2><strong>标题</strong></h2>" in rendered
    assert 'target="_blank"' in rendered
    with pytest.raises(RenderingError):
        render_tiptap({"type": "doc", "content": [{"type": "script", "text": "x"}]})
    with pytest.raises(RenderingError):
        render_tiptap(
            {
                "type": "doc",
                "attrs": {"id": "location"},
                "content": [],
            }
        )


def test_only_policy_generated_bilibili_embed_survives_and_removal_is_visible() -> None:
    source = (
        '<iframe src="https://player.bilibili.com/player.html?bvid=BV1xx411c7mD"></iframe>'
        '<kaj-embed data-source="bilibili" '
        'data-url="https://www.bilibili.com/video/BV1xx411c7mD"></kaj-embed>'
    )
    enabled = render_author_html(source)
    assert enabled.html.count("<iframe") == 1
    assert "https://player.bilibili.com/player.html?bvid=BV1xx411c7mD" in enabled.html
    assert (
        'sandbox="allow-presentation allow-same-origin allow-scripts"' in enabled.html
    )
    assert "evil" not in enabled.html

    removed = render_author_html(source, embed_policy=TrustedEmbedPolicy(()))
    assert "<iframe" not in removed.html
    assert "来源不可用" in removed.html
    assert enabled.cache_key != removed.cache_key


def test_invalid_embed_host_and_credentials_never_reach_iframe() -> None:
    rendered = render_author_html(
        '<kaj-embed data-source="bilibili" '
        'data-url="https://www.bilibili.com.evil.test/video/BV1xx411c7mD"></kaj-embed>'
        '<kaj-embed data-source="bilibili" '
        'data-url="https://user:pass@www.bilibili.com/video/BV1xx411c7mD"></kaj-embed>'
    ).html
    assert "<iframe" not in rendered
    assert "evil.test" not in rendered
    assert "user:pass" not in rendered
    assert rendered.count("来源不可用") == 2


def test_cache_key_partitions_format_policy_and_media_capabilities() -> None:
    media_id = new_ulid()
    baseline = render_author_html("<p>same</p>")
    markdown = render_markdown("<p>same</p>")
    removed_policy = render_author_html(
        "<p>same</p>", embed_policy=TrustedEmbedPolicy(())
    )
    media_capability = render_author_html("<p>same</p>", allowed_media_ids={media_id})

    assert (
        len(
            {
                baseline.cache_key,
                markdown.cache_key,
                removed_policy.cache_key,
                media_capability.cache_key,
            }
        )
        == 4
    )


def test_source_size_and_media_allowlist_inputs_are_bounded() -> None:
    with pytest.raises(RenderingError):
        render_markdown("x" * (MAX_SOURCE_BYTES + 1))
    with pytest.raises(RenderingError):
        render_author_html("<p>safe</p>", allowed_media_ids="not-a-collection")
    with pytest.raises(RenderingError):
        render_author_html("<p>safe</p>", allowed_media_ids={"not-a-ulid"})


def test_tiptap_supports_semantic_blocks_and_rejects_malformed_marks() -> None:
    media_id = new_ulid()
    document = {
        "type": "doc",
        "content": [
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "引用"},
                            {"type": "hardBreak"},
                            {
                                "type": "image",
                                "attrs": {"src": f"media:{media_id}", "alt": "图"},
                            },
                        ],
                    }
                ],
            },
            {
                "type": "orderedList",
                "attrs": {"start": 3},
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "列表"}],
                            }
                        ],
                    }
                ],
            },
            {"type": "horizontalRule"},
            {
                "type": "codeBlock",
                "attrs": {"language": "html"},
                "content": [{"type": "text", "text": "<script>x</script>"}],
            },
        ],
    }
    html = render_tiptap(document, allowed_media_ids={media_id}).html
    assert "<blockquote>" in html
    assert f'src="/_kaj/media/{media_id}"' in html
    assert '<ol start="3">' in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert "<script>" not in html

    malformed = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "duplicate",
                        "marks": [{"type": "bold"}, {"type": "bold"}],
                    }
                ],
            }
        ],
    }
    with pytest.raises(RenderingError):
        render_tiptap(malformed)


def test_import_preview_rejects_invalid_formats_and_tiptap_json() -> None:
    with pytest.raises(RenderingError):
        render_import_preview("safe", "unknown")
    with pytest.raises(RenderingError):
        render_import_preview("{", ContentFormat.TIPTAP)


def test_external_links_with_credentials_are_reduced_to_plain_links() -> None:
    html = render_author_html(
        '<a href="https://user:pass@example.com/private">credentials</a>'
    ).html
    assert html == "<a>credentials</a>"
