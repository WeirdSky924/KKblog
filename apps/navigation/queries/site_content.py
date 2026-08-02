from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.cache import cache

from apps.accounts.public import is_administrator

from ..media_gateway import NavigationMediaError, navigation_media_gateway
from ..models import FriendLink, SiteConfiguration, StaticPage, TrustedEmbedSource

PUBLIC_SITE_CONFIGURATION_CACHE_KEY = "kaj:navigation:site-configuration:v2"
PUBLIC_SITE_CONFIGURATION_CACHE_SECONDS = 300


class SiteContentQueryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SiteConfigurationItem:
    site_name: str
    site_description: str
    copyright_text: str
    registration_enabled: bool
    article_body_max_bytes: int
    logo_asset_id: str | None
    verification_email_template: str
    backup_destination: str
    row_version: int

    @property
    def logo_url(self) -> str | None:
        return f"/_kaj/media/{self.logo_asset_id}" if self.logo_asset_id else None


@dataclass(frozen=True, slots=True)
class StaticPageItem:
    page_type: str
    page_type_label: str
    content_format: str
    content_format_label: str
    source: str
    published: bool
    row_version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PublishedStaticPage:
    page_type: str
    title: str
    html: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FriendLinkItem:
    id: UUID
    name: str
    url: str
    description: str
    logo_asset_id: str
    position: int
    row_version: int

    @property
    def logo_url(self) -> str:
        return f"/_kaj/media/{self.logo_asset_id}"


@dataclass(frozen=True, slots=True)
class TrustedEmbedSourceItem:
    source_key: str
    display_name: str
    host_pattern: str
    enabled: bool
    row_version: int


@dataclass(frozen=True, slots=True)
class AdminSiteSettings:
    configuration: SiteConfigurationItem
    static_pages: tuple[StaticPageItem, ...]
    friend_links: tuple[FriendLinkItem, ...]
    trusted_sources: tuple[TrustedEmbedSourceItem, ...]


def _configuration_item(row: SiteConfiguration) -> SiteConfigurationItem:
    return SiteConfigurationItem(
        site_name=row.site_name,
        site_description=row.site_description,
        copyright_text=row.copyright_text,
        registration_enabled=row.registration_enabled,
        article_body_max_bytes=row.article_body_max_bytes,
        logo_asset_id=row.logo_asset_id,
        verification_email_template=row.verification_email_template,
        backup_destination=row.backup_destination,
        row_version=row.row_version,
    )


def public_site_configuration() -> SiteConfigurationItem:
    try:
        row = SiteConfiguration.objects.only(
            "site_name",
            "site_description",
            "copyright_text",
            "registration_enabled",
            "article_body_max_bytes",
            "logo_asset_id",
            "verification_email_template",
            "backup_destination",
            "row_version",
        ).get(pk=1)
    except SiteConfiguration.DoesNotExist:
        raise SiteContentQueryError("Site configuration is missing") from None
    cached = cache.get(PUBLIC_SITE_CONFIGURATION_CACHE_KEY)
    if (
        isinstance(cached, tuple)
        and len(cached) == 2
        and cached[0] == row.row_version
        and isinstance(cached[1], SiteConfigurationItem)
    ):
        return cached[1]
    item = _configuration_item(row)
    cache.set(
        PUBLIC_SITE_CONFIGURATION_CACHE_KEY,
        (row.row_version, item),
        PUBLIC_SITE_CONFIGURATION_CACHE_SECONDS,
    )
    return item


def invalidate_public_site_configuration_cache() -> None:
    cache.delete(PUBLIC_SITE_CONFIGURATION_CACHE_KEY)


def registration_enabled() -> bool:
    return public_site_configuration().registration_enabled


def article_body_max_bytes() -> int:
    return public_site_configuration().article_body_max_bytes


def _static_item(row: StaticPage) -> StaticPageItem:
    return StaticPageItem(
        page_type=row.page_type,
        page_type_label=row.get_page_type_display(),
        content_format=row.content_format,
        content_format_label=row.get_content_format_display(),
        source=row.source,
        published=row.published,
        row_version=row.row_version,
        updated_at=row.updated_at,
    )


def static_page_is_published(page_type: StaticPage.PageType | str) -> bool:
    try:
        normalized = StaticPage.PageType(page_type)
    except (TypeError, ValueError):
        return False
    return (
        StaticPage.objects.filter(
            page_type=normalized,
            published=True,
        )
        .exclude(source="")
        .exists()
    )


def published_static_page(
    page_type: StaticPage.PageType | str,
) -> PublishedStaticPage | None:
    try:
        normalized = StaticPage.PageType(page_type)
    except (TypeError, ValueError):
        return None
    row = (
        StaticPage.objects.filter(
            page_type=normalized,
            published=True,
        )
        .exclude(source="")
        .first()
    )
    if row is None:
        return None
    try:
        rendered = (
            navigation_media_gateway().render_markdown(row.source)
            if row.content_format == StaticPage.ContentFormat.MARKDOWN
            else navigation_media_gateway().render_rich_text(row.source)
        )
    except NavigationMediaError:
        raise SiteContentQueryError("Static page could not be rendered") from None
    return PublishedStaticPage(
        page_type=row.page_type,
        title=row.get_page_type_display(),
        html=rendered,
        updated_at=row.updated_at,
    )


def visible_friend_links() -> tuple[FriendLinkItem, ...]:
    return tuple(
        FriendLinkItem(
            id=row.id,
            name=row.name,
            url=row.url,
            description=row.description,
            logo_asset_id=row.logo_asset_id,
            position=row.position,
            row_version=row.row_version,
        )
        for row in FriendLink.objects.all().order_by("position", "id")
    )


def trusted_embed_source_keys() -> tuple[str, ...]:
    return tuple(
        TrustedEmbedSource.objects.filter(enabled=True)
        .order_by("source_key")
        .values_list("source_key", flat=True)
    )


def admin_site_settings(*, actor_id) -> AdminSiteSettings:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator site settings access denied")
    configuration = public_site_configuration()
    pages = tuple(
        _static_item(row) for row in StaticPage.objects.all().order_by("page_type")
    )
    links = visible_friend_links()
    sources = tuple(
        TrustedEmbedSourceItem(
            source_key=row.source_key,
            display_name=row.display_name,
            host_pattern=row.host_pattern,
            enabled=row.enabled,
            row_version=row.row_version,
        )
        for row in TrustedEmbedSource.objects.all().order_by("source_key")
    )
    return AdminSiteSettings(configuration, pages, links, sources)


__all__ = [
    "AdminSiteSettings",
    "FriendLinkItem",
    "PublishedStaticPage",
    "SiteConfigurationItem",
    "SiteContentQueryError",
    "StaticPageItem",
    "TrustedEmbedSourceItem",
    "admin_site_settings",
    "article_body_max_bytes",
    "invalidate_public_site_configuration_cache",
    "public_site_configuration",
    "published_static_page",
    "registration_enabled",
    "static_page_is_published",
    "trusted_embed_source_keys",
    "visible_friend_links",
]
