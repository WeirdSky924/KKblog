from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from urllib.parse import urlsplit

_BILIBILI_VIDEO_PATH = re.compile(r"/video/(BV[A-Za-z0-9]{10,20})/?")


@dataclass(frozen=True, slots=True)
class TrustedEmbedProjection:
    source: str
    resource_id: str
    canonical_url: str
    player_url: str


@dataclass(frozen=True, slots=True)
class TrustedEmbedPolicy:
    enabled_sources: tuple[str, ...] = ("bilibili",)

    def __post_init__(self) -> None:
        normalized = tuple(
            sorted({source.casefold() for source in self.enabled_sources})
        )
        if any(not source or not source.isascii() for source in normalized):
            raise ValueError("Trusted embed source names must be non-empty ASCII")
        object.__setattr__(self, "enabled_sources", normalized)

    @property
    def fingerprint(self) -> str:
        joined = "\0".join(self.enabled_sources).encode()
        return sha256(joined).hexdigest()

    def project(self, source: str, url: str) -> TrustedEmbedProjection | None:
        normalized_source = source.casefold()
        if normalized_source not in self.enabled_sources:
            return None
        return _project_known_source(normalized_source, url)

    def render(self, source: str, url: str) -> str | None:
        projection = self.project(source, url)
        if projection is None:
            return None
        return _render_projection(projection)

    def fallback(self, source: str, url: str) -> str | None:
        projection = _project_known_source(source.casefold(), url)
        if projection is None:
            return None
        safe_source = escape(projection.source, quote=True)
        safe_url = escape(projection.canonical_url, quote=True)
        return (
            f'<aside data-kaj-embed-fallback="{safe_source}" role="note">'
            "<span>当前无法播放此内容。</span>"
            f'<a href="{safe_url}" target="_blank" '
            'rel="noopener noreferrer">在 Bilibili 打开</a></aside>'
        )


TrustedEmbedPolicyProvider = Callable[[], TrustedEmbedPolicy]


def _default_trusted_embed_policy() -> TrustedEmbedPolicy:
    return TrustedEmbedPolicy()


_trusted_embed_policy_provider: TrustedEmbedPolicyProvider = (
    _default_trusted_embed_policy
)


def configure_trusted_embed_policy_provider(
    provider: TrustedEmbedPolicyProvider,
) -> None:
    if not callable(provider):
        raise TypeError("trusted embed policy provider must be callable")
    global _trusted_embed_policy_provider
    _trusted_embed_policy_provider = provider


def configured_trusted_embed_policy() -> TrustedEmbedPolicy:
    policy = _trusted_embed_policy_provider()
    if not isinstance(policy, TrustedEmbedPolicy):
        raise TypeError("trusted embed policy provider returned an invalid value")
    return policy


def _project_known_source(
    source: str,
    url: str,
) -> TrustedEmbedProjection | None:
    if source != "bilibili":
        return None
    return _project_bilibili(url)


def _project_bilibili(url: str) -> TrustedEmbedProjection | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.bilibili.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    match = _BILIBILI_VIDEO_PATH.fullmatch(parsed.path)
    if match is None:
        return None
    resource_id = match.group(1)
    return TrustedEmbedProjection(
        source="bilibili",
        resource_id=resource_id,
        canonical_url=f"https://www.bilibili.com/video/{resource_id}",
        player_url=(f"https://player.bilibili.com/player.html?bvid={resource_id}"),
    )


def _render_projection(projection: TrustedEmbedProjection) -> str:
    safe_source = escape(projection.source, quote=True)
    safe_player_url = escape(projection.player_url, quote=True)
    safe_canonical_url = escape(projection.canonical_url, quote=True)
    return (
        f'<figure data-kaj-embed-card="{safe_source}">'
        '<div data-kaj-embed-frame="true">'
        f'<iframe src="{safe_player_url}" title="Bilibili 视频" loading="lazy" '
        'referrerpolicy="no-referrer" sandbox="allow-presentation allow-same-origin '
        'allow-scripts" allowfullscreen></iframe></div>'
        "<figcaption>"
        f'<a href="{safe_canonical_url}" target="_blank" '
        'rel="noopener noreferrer">在 Bilibili 打开</a>'
        "</figcaption></figure>"
    )
