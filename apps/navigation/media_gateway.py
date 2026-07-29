from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID


class NavigationMediaError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class NavigationMediaGateway:
    replace_site_logo: Callable[[UUID, str | None], None]
    replace_friend_logo: Callable[[UUID, str, str], None]
    release_friend_logo: Callable[[str], None]
    render_markdown: Callable[[str], str]
    render_rich_text: Callable[[str], str]

    def __post_init__(self) -> None:
        if not all(
            callable(port)
            for port in (
                self.replace_site_logo,
                self.replace_friend_logo,
                self.release_friend_logo,
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
    "configure_navigation_media_gateway",
    "navigation_media_gateway",
]
