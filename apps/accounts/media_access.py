from uuid import UUID

from apps.media.public import (
    MediaPurpose,
    MediaTargetType,
    MediaUploadAdapter,
    TargetAccessDecision,
    TargetAccessRequest,
    register_media_upload_adapter,
    register_target_access,
)

from .models import Account


def account_profile_media_access(
    request: TargetAccessRequest,
) -> TargetAccessDecision:
    try:
        account_id = UUID(request.target_id)
    except (TypeError, ValueError):
        return TargetAccessDecision(False, False, False, False)
    active = Account.objects.filter(
        id=account_id, status=Account.Status.ACTIVE
    ).exists()
    owner = active and request.actor_id == account_id
    return TargetAccessDecision(
        exists=active,
        can_bind=owner,
        can_read=active,
        public_immutable=active,
    )


def register_media_access() -> None:
    register_target_access(
        MediaTargetType.ACCOUNT_PROFILE,
        account_profile_media_access,
        replace=True,
    )
    register_media_upload_adapter(
        MediaUploadAdapter(
            key="avatar",
            purpose=MediaPurpose.AVATAR,
            input_name="avatar_asset_id",
            access=lambda actor_id: isinstance(actor_id, UUID),
        ),
        replace=True,
    )
