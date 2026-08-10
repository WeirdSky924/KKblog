import pytest

from apps.media.rendering import TipTapSchemaError, TrustedEmbedPolicy, render_tiptap


def _document(source: str, url: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "embed", "attrs": {"source": source, "url": url}}],
    }


def test_bilibili_policy_owns_canonical_projection_and_safe_card() -> None:
    policy = TrustedEmbedPolicy(("bilibili",))

    projection = policy.project(
        "BILIBILI",
        "https://www.bilibili.com/video/BV1xx411c7mD/",
    )

    assert projection is not None
    assert projection.source == "bilibili"
    assert projection.resource_id == "BV1xx411c7mD"
    assert projection.canonical_url == ("https://www.bilibili.com/video/BV1xx411c7mD")
    assert projection.player_url == (
        "https://player.bilibili.com/player.html?bvid=BV1xx411c7mD"
    )
    rendered = policy.render(projection.source, projection.canonical_url)
    assert rendered is not None
    assert 'data-kaj-embed-card="bilibili"' in rendered
    assert 'sandbox="allow-presentation allow-same-origin allow-scripts"' in rendered
    assert 'referrerpolicy="no-referrer"' in rendered
    assert 'loading="lazy"' in rendered
    assert 'href="https://www.bilibili.com/video/BV1xx411c7mD"' in rendered
    assert 'rel="noopener noreferrer"' in rendered
    assert 'target="_blank"' in rendered


@pytest.mark.parametrize(
    "url",
    [
        "http://www.bilibili.com/video/BV1xx411c7mD",
        "//www.bilibili.com/video/BV1xx411c7mD",
        "https://bilibili.com/video/BV1xx411c7mD",
        "https://www.bilibili.com.evil.test/video/BV1xx411c7mD",
        "https://user@www.bilibili.com/video/BV1xx411c7mD",
        "https://user:pass@www.bilibili.com/video/BV1xx411c7mD",
        "https://www.bilibili.com:443/video/BV1xx411c7mD",
        "https://www.bilibili.com/video/BV1xx411c7mD/extra",
        "https://www.bilibili.com/video/?bvid=BV1xx411c7mD",
        "https://www.bilibili.com/video/BV1xx411c7mD?redirect=evil.test",
        "https://www.bilibili.com/video/BV1xx411c7mD#chapter",
    ],
)
def test_bilibili_policy_rejects_host_protocol_and_path_confusion(url: str) -> None:
    policy = TrustedEmbedPolicy(("bilibili",))

    assert policy.project("bilibili", url) is None
    assert policy.render("bilibili", url) is None
    assert policy.fallback("bilibili", url) is None


def test_disabled_known_source_has_safe_historical_fallback() -> None:
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    policy = TrustedEmbedPolicy(())

    assert policy.project("bilibili", url) is None
    assert policy.render("bilibili", url) is None
    fallback = policy.fallback("bilibili", url)
    assert fallback is not None
    assert 'data-kaj-embed-fallback="bilibili"' in fallback
    assert f'href="{url}"' in fallback
    assert "当前无法播放" in fallback


def test_unknown_or_invalid_sources_never_expose_user_urls() -> None:
    malicious = "https://evil.test/private?token=secret"
    policy = TrustedEmbedPolicy(())

    assert policy.fallback("unknown", malicious) is None
    rendered = render_tiptap(
        _document("unknown", malicious),
        schema_version=2,
        embed_policy=policy,
        unavailable_resources="placeholder",
    ).html
    assert rendered == '<span role="note">来源不可用</span>'
    assert "evil.test" not in rendered
    assert "secret" not in rendered


def test_disabled_embed_rejects_strict_save_but_read_and_export_degrade() -> None:
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    document = _document("bilibili", url)
    policy = TrustedEmbedPolicy(())

    with pytest.raises(TipTapSchemaError) as captured:
        render_tiptap(document, schema_version=2, embed_policy=policy)
    assert captured.value.code == "media.tiptap.embed_invalid.v1"

    historical = render_tiptap(
        document,
        schema_version=2,
        embed_policy=policy,
        unavailable_resources="placeholder",
    ).html
    assert 'data-kaj-embed-fallback="bilibili"' in historical
    assert f'href="{url}"' in historical

    exported = render_tiptap(
        document,
        schema_version=2,
        embed_policy=policy,
        unavailable_resources="omit",
    ).html
    assert exported == ""
