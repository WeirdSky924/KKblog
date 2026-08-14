from uuid import UUID

from apps.accounts.policies.registration import configure_registration_policy_provider
from apps.accounts.public import is_administrator
from apps.content.rendering_policy import configure_content_embed_policy_provider
from apps.content.snapshots import configure_article_body_limit_provider
from apps.media.public import (
    BindingInput,
    MediaAccessError,
    MediaBindingError,
    MediaPurpose,
    MediaTargetType,
    RenderingError,
    TargetAccessDecision,
    TargetAccessRequest,
    TrustedEmbedPolicy,
    authorize_asset_read,
    register_target_access,
    release_target_assets,
    render_author_html,
    render_markdown,
    replace_bindings,
)
from apps.navigation.media_gateway import (
    NavigationMediaError,
    NavigationMediaGateway,
    NavigationMediaReference,
    configure_navigation_media_gateway,
)
from apps.navigation.models import SiteConfiguration
from apps.navigation.queries import (
    article_body_max_bytes,
    registration_enabled,
    trusted_embed_source_keys,
)


def _site_brand_access(request: TargetAccessRequest) -> TargetAccessDecision:
    exists = (
        request.target_id == "site" and SiteConfiguration.objects.filter(pk=1).exists()
    )
    return TargetAccessDecision(
        exists=exists,
        can_bind=exists and is_administrator(request.actor_id),
        can_read=exists,
        public_immutable=True,
    )


def _media_error(error: MediaBindingError | RenderingError) -> NavigationMediaError:
    return NavigationMediaError(
        getattr(error, "code", "navigation.rendering_invalid.v1"),
        getattr(error, "safe_message", "站点图片或正文无法安全处理。"),
    )


def _replace_site_logo(actor_id: UUID, asset_id: str | None) -> None:
    try:
        replace_bindings(
            actor_id=actor_id,
            target_type=MediaTargetType.SITE_BRAND,
            target_id="site",
            inputs=(BindingInput(asset_id, "logo"),) if asset_id else (),
            purpose=MediaPurpose.LOGO,
        )
    except MediaBindingError as error:
        raise _media_error(error) from None


def _replace_site_hero(actor_id: UUID, asset_id: str | None) -> None:
    try:
        replace_bindings(
            actor_id=actor_id,
            target_type=MediaTargetType.SITE_BRAND,
            target_id="site",
            inputs=(BindingInput(asset_id, "hero"),) if asset_id else (),
            purpose=MediaPurpose.HERO,
        )
    except MediaBindingError as error:
        raise _media_error(error) from None


def _resolve_site_media(asset_id: str) -> NavigationMediaReference | None:
    try:
        asset = authorize_asset_read(actor_id=None, asset_id=asset_id)
    except MediaAccessError:
        return None
    return NavigationMediaReference(asset.asset_id, asset.detected_mime)


def _release_friend_legacy_media(target_id: str) -> None:
    release_target_assets(
        target_type=MediaTargetType.FRIEND_LINK,
        target_ids=(target_id,),
    )


def _render_markdown(source: str) -> str:
    try:
        return render_markdown(source, embed_policy=_trusted_embed_policy()).html
    except RenderingError as error:
        raise _media_error(error) from None


def _render_rich_text(source: str) -> str:
    try:
        return render_author_html(source, embed_policy=_trusted_embed_policy()).html
    except RenderingError as error:
        raise _media_error(error) from None


def _trusted_embed_policy() -> TrustedEmbedPolicy:
    return TrustedEmbedPolicy(trusted_embed_source_keys())


def configure_navigation_integrations() -> None:
    configure_registration_policy_provider(registration_enabled)
    configure_article_body_limit_provider(article_body_max_bytes)
    configure_content_embed_policy_provider(_trusted_embed_policy)
    configure_navigation_media_gateway(
        NavigationMediaGateway(
            replace_site_logo=_replace_site_logo,
            replace_site_hero=_replace_site_hero,
            resolve_site_media=_resolve_site_media,
            release_friend_legacy_media=_release_friend_legacy_media,
            render_markdown=_render_markdown,
            render_rich_text=_render_rich_text,
        )
    )
    register_target_access(
        MediaTargetType.SITE_BRAND,
        _site_brand_access,
        replace=True,
    )


__all__ = ["configure_navigation_integrations"]
