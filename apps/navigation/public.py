from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.module_loading import import_string

from .site_contracts import (
    SITE_MAX_ARTICLE_BODY_BYTES,
    SITE_MIN_ARTICLE_BODY_BYTES,
    STATIC_PAGE_FORMAT_CHOICES,
    STATIC_PAGE_TYPE_CHOICES,
)
from .validators import require_safe_navigation_url

if TYPE_CHECKING:
    from .queries import (
        AdminNavigationNode,
        AdminNavigationTree,
        AdminSiteSettings,
        FriendLinkItem,
        NavigationTreeQueryError,
        PublishedStaticPage,
        SiteConfigurationItem,
        SiteContentQueryError,
        admin_navigation_tree,
        admin_site_settings,
        article_body_max_bytes,
        public_navigation_tree,
        published_static_page,
        registration_enabled,
        visible_friend_links,
    )
    from .services import (
        NavigationCommandError,
        NavigationDeleteResult,
        NavigationNodeResult,
        SiteConfigurationResult,
        SiteContentCommandError,
        StaticPageResult,
        TrustedSourceResult,
        VerificationEmailTemplateResult,
        create_friend_link,
        create_navigation_node,
        delete_friend_link,
        delete_navigation_subtree,
        edit_navigation_node,
        move_navigation_subtree,
        set_navigation_node_hidden,
        set_trusted_embed_source,
        update_friend_link,
        update_site_configuration,
        update_static_page,
        update_verification_email_template,
    )


@dataclass(frozen=True, slots=True)
class NavigationItem:
    label: str
    url: str
    children: tuple["NavigationItem", ...] = ()
    key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("Navigation label is required")
        if len(self.label) > 80:
            raise ValueError("Navigation label is too long")
        require_safe_navigation_url(self.url)
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
                require_safe_navigation_url(value)
                if urlsplit(value).scheme:
                    raise ValueError("Site presentation links must be site-relative")
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
    "AdminNavigationNode",
    "AdminNavigationTree",
    "AdminSiteSettings",
    "FriendLinkItem",
    "NavigationCommandError",
    "NavigationDeleteResult",
    "NavigationItem",
    "NavigationNodeResult",
    "NavigationTreeQueryError",
    "PublishedStaticPage",
    "SITE_MAX_ARTICLE_BODY_BYTES",
    "SITE_MIN_ARTICLE_BODY_BYTES",
    "STATIC_PAGE_FORMAT_CHOICES",
    "STATIC_PAGE_TYPE_CHOICES",
    "SiteConfigurationItem",
    "SiteConfigurationResult",
    "SiteContentCommandError",
    "SiteContentQueryError",
    "VerificationEmailTemplateResult",
    "SitePresentation",
    "StaticPageResult",
    "TrustedSourceResult",
    "admin_site_settings",
    "admin_navigation_tree",
    "article_body_max_bytes",
    "create_friend_link",
    "create_navigation_node",
    "default_site_presentation",
    "delete_navigation_subtree",
    "delete_friend_link",
    "edit_navigation_node",
    "move_navigation_subtree",
    "public_navigation_tree",
    "published_static_page",
    "public_site_presentation",
    "registration_enabled",
    "set_trusted_embed_source",
    "set_navigation_node_hidden",
    "update_friend_link",
    "update_site_configuration",
    "update_verification_email_template",
    "update_static_page",
    "visible_friend_links",
]

_LAZY_EXPORTS = {
    "AdminSiteSettings": ("apps.navigation.queries", "AdminSiteSettings"),
    "AdminNavigationNode": ("apps.navigation.queries", "AdminNavigationNode"),
    "AdminNavigationTree": ("apps.navigation.queries", "AdminNavigationTree"),
    "FriendLinkItem": ("apps.navigation.queries", "FriendLinkItem"),
    "NavigationTreeQueryError": (
        "apps.navigation.queries",
        "NavigationTreeQueryError",
    ),
    "PublishedStaticPage": ("apps.navigation.queries", "PublishedStaticPage"),
    "SiteConfigurationItem": (
        "apps.navigation.queries",
        "SiteConfigurationItem",
    ),
    "SiteContentQueryError": (
        "apps.navigation.queries",
        "SiteContentQueryError",
    ),
    "admin_site_settings": ("apps.navigation.queries", "admin_site_settings"),
    "article_body_max_bytes": (
        "apps.navigation.queries",
        "article_body_max_bytes",
    ),
    "published_static_page": ("apps.navigation.queries", "published_static_page"),
    "registration_enabled": ("apps.navigation.queries", "registration_enabled"),
    "visible_friend_links": ("apps.navigation.queries", "visible_friend_links"),
    "admin_navigation_tree": ("apps.navigation.queries", "admin_navigation_tree"),
    "public_navigation_tree": ("apps.navigation.queries", "public_navigation_tree"),
    "NavigationCommandError": (
        "apps.navigation.services",
        "NavigationCommandError",
    ),
    "SiteConfigurationResult": (
        "apps.navigation.services",
        "SiteConfigurationResult",
    ),
    "SiteContentCommandError": (
        "apps.navigation.services",
        "SiteContentCommandError",
    ),
    "VerificationEmailTemplateResult": (
        "apps.navigation.services",
        "VerificationEmailTemplateResult",
    ),
    "StaticPageResult": ("apps.navigation.services", "StaticPageResult"),
    "TrustedSourceResult": (
        "apps.navigation.services",
        "TrustedSourceResult",
    ),
    "create_friend_link": ("apps.navigation.services", "create_friend_link"),
    "NavigationDeleteResult": (
        "apps.navigation.services",
        "NavigationDeleteResult",
    ),
    "NavigationNodeResult": ("apps.navigation.services", "NavigationNodeResult"),
    "create_navigation_node": (
        "apps.navigation.services",
        "create_navigation_node",
    ),
    "delete_friend_link": ("apps.navigation.services", "delete_friend_link"),
    "delete_navigation_subtree": (
        "apps.navigation.services",
        "delete_navigation_subtree",
    ),
    "edit_navigation_node": ("apps.navigation.services", "edit_navigation_node"),
    "move_navigation_subtree": (
        "apps.navigation.services",
        "move_navigation_subtree",
    ),
    "set_navigation_node_hidden": (
        "apps.navigation.services",
        "set_navigation_node_hidden",
    ),
    "set_trusted_embed_source": (
        "apps.navigation.services",
        "set_trusted_embed_source",
    ),
    "update_friend_link": ("apps.navigation.services", "update_friend_link"),
    "update_site_configuration": (
        "apps.navigation.services",
        "update_site_configuration",
    ),
    "update_verification_email_template": (
        "apps.navigation.services",
        "update_verification_email_template",
    ),
    "update_static_page": ("apps.navigation.services", "update_static_page"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(name) from None
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
