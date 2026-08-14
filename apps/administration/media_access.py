from uuid import UUID

from apps.accounts.public import is_administrator
from apps.media.public import (
    MediaPurpose,
    MediaUploadAdapter,
    register_media_upload_adapter,
)


def _administrator_only(actor_id: UUID | None) -> bool:
    return is_administrator(actor_id)


def register_media_access() -> None:
    register_media_upload_adapter(
        MediaUploadAdapter(
            key="site-logo",
            purpose=MediaPurpose.LOGO,
            input_name="logo_asset_id",
            access=_administrator_only,
        ),
        replace=True,
    )
    register_media_upload_adapter(
        MediaUploadAdapter(
            key="site-hero",
            purpose=MediaPurpose.HERO,
            input_name="hero_asset_id",
            access=_administrator_only,
        ),
        replace=True,
    )
    register_media_upload_adapter(
        MediaUploadAdapter(
            key="section-cover",
            purpose=MediaPurpose.SECTION_COVER,
            input_name="default_cover_asset_id",
            access=_administrator_only,
        ),
        replace=True,
    )
