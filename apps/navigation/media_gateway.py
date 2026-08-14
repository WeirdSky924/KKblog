from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from apps.core.ids import is_ulid


class NavigationMediaError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class NavigationMediaReference:
    asset_id: str
    detected_mime: str

    def __post_init__(self) -> None:
        if not is_ulid(self.asset_id) or self.detected_mime not in {
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "video/mp4",
            "video/webm",
        }:
            raise ValueError("Invalid site media reference")

    @property
    def url(self) -> str:
        return f"/_kaj/media/{self.asset_id}"

    @property
    def is_video(self) -> bool:
        return self.detected_mime.startswith("video/")


@dataclass(frozen=True, slots=True)
class NavigationMediaGateway:
    replace_site_logo: Callable[[UUID, str | None], None]
    replace_site_hero: Callable[[UUID, str | None], None]
    resolve_site_media: Callable[[str], NavigationMediaReference | None]
    release_friend_legacy_media: Callable[[str], None]
    render_markdown: Callable[[str], str]
    render_rich_text: Callable[[str], str]

    def __post_init__(self) -> None:
        if not all(
            callable(port)
            for port in (
                self.replace_site_logo,
                self.replace_site_hero,
                self.resolve_site_media,
                self.release_friend_legacy_media,
                self.render_markdown,
                self.render_rich_text,
            )
        ):
            raise TypeError("navigation media gateway ports must be callable")


def _unavailable(*args, **kwargs) -> None:
    del args, kwargs
    raise NavigationMediaError(
        "navigation.media_gateway_unavailable.v1",
        "站点图片服务暂时不可用。",
    )


_gateway = NavigationMediaGateway(
    _unavailable,
    _unavailable,
    _unavailable,
    _unavailable,
    _unavailable,
    _unavailable,
)


def configure_navigation_media_gateway(gateway: NavigationMediaGateway) -> None:
    if not isinstance(gateway, NavigationMediaGateway):
        raise TypeError("gateway must be a NavigationMediaGateway")
    global _gateway
    _gateway = gateway


def navigation_media_gateway() -> NavigationMediaGateway:
    return _gateway


__all__ = [
    "NavigationMediaError",
    "NavigationMediaGateway",
    "NavigationMediaReference",
    "configure_navigation_media_gateway",
    "navigation_media_gateway",
]
