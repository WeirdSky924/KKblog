from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.module_loading import import_string


def _require_safe_url(value: str, *, allow_https: bool = True) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(character in value for character in ("\\", "\r", "\n", "\x00"))
    ):
        raise ValueError("URL must be a safe site-relative or HTTPS URL")
    parsed = urlsplit(value)
    is_site_relative = (
        value.startswith("/")
        and not value.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
    )
    is_https = parsed.scheme == "https" and bool(parsed.netloc)
    if not (is_site_relative or (allow_https and is_https)):
        raise ValueError("URL must be a safe site-relative or HTTPS URL")


@dataclass(frozen=True, slots=True)
class NavigationItem:
    label: str
    url: str
    children: tuple["NavigationItem", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("Navigation label is required")
        if len(self.label) > 80:
            raise ValueError("Navigation label is too long")
        _require_safe_url(self.url)
        if not isinstance(self.children, tuple) or not all(
            isinstance(child, NavigationItem) for child in self.children
        ):
            raise TypeError("Navigation children must be NavigationItem values")

    @property
    def external(self) -> bool:
        return urlsplit(self.url).scheme == "https"


@dataclass(frozen=True, slots=True)
class SitePresentation:
    site_name: str
    site_description: str | None
    logo_url: str | None
    navigation: tuple[NavigationItem, ...]
    copyright_text: str | None
    privacy_url: str | None
    terms_url: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.site_name, str) or not self.site_name.strip():
            raise ValueError("Site name is required")
        if len(self.site_name) > 100:
            raise ValueError("Site name is too long")
        if not isinstance(self.navigation, tuple) or not all(
            isinstance(item, NavigationItem) for item in self.navigation
        ):
            raise TypeError("Navigation must contain NavigationItem values")
        for value in (self.logo_url, self.privacy_url, self.terms_url):
            if value is not None:
                _require_safe_url(value, allow_https=False)
        _require_navigation_depth(self.navigation)


def _require_navigation_depth(
    items: tuple[NavigationItem, ...], *, depth: int = 1
) -> None:
    if depth > 3:
        raise ValueError("Navigation supports at most three levels")
    for item in items:
        if item.children:
            _require_navigation_depth(item.children, depth=depth + 1)


def default_site_presentation() -> SitePresentation:
    return SitePresentation(
        site_name="Kaj的小房间",
        site_description=None,
        logo_url=None,
        navigation=(),
        copyright_text=None,
        privacy_url=None,
        terms_url=None,
    )


def public_site_presentation() -> SitePresentation:
    provider_path = settings.NAVIGATION_SITE_PRESENTATION_PROVIDER
    provider = import_string(provider_path)
    presentation = provider()
    if not isinstance(presentation, SitePresentation):
        raise TypeError("Site presentation provider returned an invalid value")
    return presentation


__all__ = [
    "NavigationItem",
    "SitePresentation",
    "default_site_presentation",
    "public_site_presentation",
]
