from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.core.ids import is_ulid
from apps.media.models import MediaAsset, MediaPurpose, MediaState
from apps.media.targets import (
    TargetAccessOperation,
    TargetAccessRegistry,
    TargetAccessRequest,
    default_target_access_registry,
)


class MediaAccessError(LookupError):
    def __init__(self) -> None:
        self.code = "media.not_found.v1"
        super().__init__("未找到请求的图片。")


@dataclass(frozen=True, slots=True)
class AssetReadAuthorization:
    asset_id: str
    storage_key: str
    detected_mime: str
    size_bytes: int
    width: int
    height: int
    public_immutable: bool


def authorize_asset_read(
    *,
    actor_id: UUID | None,
    asset_id: str,
    registry: TargetAccessRegistry = default_target_access_registry,
) -> AssetReadAuthorization:
    if actor_id is not None and not isinstance(actor_id, UUID):
        raise MediaAccessError
    if not is_ulid(asset_id):
        raise MediaAccessError
    try:
        asset = MediaAsset.objects.prefetch_related("bindings").get(
            id=asset_id, state=MediaState.ACTIVE
        )
    except MediaAsset.DoesNotExist:
        raise MediaAccessError from None
    bindings = tuple(asset.bindings.all())
    if not bindings:
        raise MediaAccessError
    for binding in bindings:
        try:
            decision = registry.decide(
                binding.target_type,
                TargetAccessRequest(
                    actor_id=actor_id,
                    target_id=binding.target_id,
                    purpose=MediaPurpose(asset.purpose),
                    operation=TargetAccessOperation.READ,
                ),
            )
        except ValidationError:
            continue
        if decision.exists and decision.can_read:
            return AssetReadAuthorization(
                asset_id=asset.id,
                storage_key=asset.storage_key,
                detected_mime=asset.detected_mime,
                size_bytes=asset.size_bytes,
                width=asset.width,
                height=asset.height,
                public_immutable=decision.public_immutable,
            )
    raise MediaAccessError
