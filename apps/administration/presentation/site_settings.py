from dataclasses import dataclass

from apps.comments.public import guestbook_comment_access
from apps.navigation.public import AdminSiteSettings

from ..forms.site_settings import (
    FriendLinkDeleteForm,
    FriendLinkForm,
    GuestbookSettingsForm,
    SiteConfigurationForm,
    StaticPageForm,
    TrustedSourceForm,
    VerificationEmailTemplateForm,
)


@dataclass(frozen=True, slots=True)
class SiteSettingsForms:
    configuration: SiteConfigurationForm
    verification_email: VerificationEmailTemplateForm
    static_pages: dict[str, StaticPageForm]
    friend_new: FriendLinkForm
    friend_links: dict[str, FriendLinkForm]
    friend_delete: dict[str, FriendLinkDeleteForm]
    trusted_sources: dict[str, TrustedSourceForm]
    guestbook: GuestbookSettingsForm


def build_site_settings_forms(
    settings: AdminSiteSettings,
    *,
    actor_id,
    data=None,
    files=None,
    bound_action: str = "",
    bound_id: str = "",
) -> SiteSettingsForms:
    def bind(action: str, identity: str = ""):
        if (
            data is not None
            and bound_action == action
            and (not identity or identity == bound_id)
        ):
            return data
        return None

    configuration = SiteConfigurationForm(
        data=bind("configuration"),
        initial={
            "site_name": settings.configuration.site_name,
            "site_description": settings.configuration.site_description,
            "copyright_text": settings.configuration.copyright_text,
            "registration_enabled": settings.configuration.registration_enabled,
            "article_body_max_bytes": settings.configuration.article_body_max_bytes,
            "logo_asset_id": settings.configuration.logo_asset_id or "",
            "backup_destination": settings.configuration.backup_destination,
            "expected_version": settings.configuration.row_version,
        },
    )
    verification_email = VerificationEmailTemplateForm(
        data=bind("verification_email"),
        files=files if bind("verification_email") is not None else None,
        initial={
            "mode": "upload",
            "expected_version": settings.configuration.row_version,
        },
    )
    static_pages = {}
    for page in settings.static_pages:
        static_pages[page.page_type] = StaticPageForm(
            prefix=f"page-{page.page_type.lower()}",
            data=bind("static_page", page.page_type),
            initial={
                "page_type": page.page_type,
                "content_format": page.content_format,
                "source": page.source,
                "expected_version": page.row_version,
            },
        )
    friend_new = FriendLinkForm(
        prefix="friend-new",
        data=bind("friend_create"),
        initial={"position": len(settings.friend_links)},
    )
    friend_links = {}
    friend_delete = {}
    for link in settings.friend_links:
        key = str(link.id)
        friend_links[key] = FriendLinkForm(
            prefix=f"friend-{key}",
            data=bind("friend_update", key),
            initial={
                "link_id": key,
                "name": link.name,
                "url": link.url,
                "description": link.description,
                "logo_asset_id": link.logo_asset_id,
                "position": link.position,
                "expected_version": link.row_version,
            },
        )
        friend_delete[key] = FriendLinkDeleteForm(
            prefix=f"delete-{key}",
            data=bind("friend_delete", key),
            initial={"link_id": key, "expected_version": link.row_version},
        )
    trusted_sources = {}
    for source in settings.trusted_sources:
        trusted_sources[source.source_key] = TrustedSourceForm(
            prefix=f"trusted-{source.source_key}",
            data=bind("trusted_source", source.source_key),
            initial={
                "source_key": source.source_key,
                "enabled": source.enabled,
                "expected_version": source.row_version,
            },
        )
    access = guestbook_comment_access(actor_id=actor_id)
    guestbook = GuestbookSettingsForm(
        data=bind("guestbook"),
        initial={
            "comments_enabled": access.comments_enabled,
            "post_login_required": access.post_login_required,
        },
    )
    return SiteSettingsForms(
        configuration=configuration,
        verification_email=verification_email,
        static_pages=static_pages,
        friend_new=friend_new,
        friend_links=friend_links,
        friend_delete=friend_delete,
        trusted_sources=trusted_sources,
        guestbook=guestbook,
    )


__all__ = ["SiteSettingsForms", "build_site_settings_forms"]
