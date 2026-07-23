from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from urllib.parse import urlsplit

_BILIBILI_VIDEO_PATH = re.compile(r"/video/(BV[A-Za-z0-9]{10,20})/?")


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

    def render(self, source: str, url: str) -> str | None:
        normalized_source = source.casefold()
        if normalized_source not in self.enabled_sources:
            return None
        if normalized_source == "bilibili":
            return _render_bilibili(url)
        return None


def _render_bilibili(url: str) -> str | None:
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
    ):
        return None
    match = _BILIBILI_VIDEO_PATH.fullmatch(parsed.path)
    if match is None:
        return None
    player_url = (
        "https://player.bilibili.com/player.html?bvid="
        f"{escape(match.group(1), quote=True)}"
    )
    return (
        f'<iframe src="{player_url}" title="Bilibili 视频" loading="lazy" '
        'referrerpolicy="no-referrer" '
        'sandbox="allow-presentation allow-same-origin allow-scripts" '
        "allowfullscreen></iframe>"
    )
