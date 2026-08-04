from uuid import UUID

from apps.accounts.public import can_upload_attachments
from apps.content.public import authoring_access
from apps.core.ids import is_ulid
from apps.media.public import (
    MediaPurpose,
    MediaUploadAdapter,
    register_media_upload_adapter,
)


def _author_upload(actor_id: UUID | None, target_id: str) -> bool:
    return is_ulid(target_id) and authoring_access(actor_id)


def register_media_access() -> None:
    for key, purpose, input_name in (
        ("article-cover", MediaPurpose.COVER, "cover_asset_id"),
        ("article-body", MediaPurpose.BODY, "body_asset_id"),
    ):
        register_media_upload_adapter(
            MediaUploadAdapter(
                key=key,
                purpose=purpose,
                input_name=input_name,
                access=authoring_access,
                target_query_parameter="target",
                target_access=_author_upload,
            ),
            replace=True,
        )
    register_media_upload_adapter(
        MediaUploadAdapter(
            key="article-attachment",
            purpose=MediaPurpose.ATTACHMENT,
            input_name="attachment_asset_id",
            access=can_upload_attachments,
            target_query_parameter="target",
            target_access=lambda actor_id, target_id: (
                is_ulid(target_id) and can_upload_attachments(actor_id)
            ),
        ),
        replace=True,
    )
