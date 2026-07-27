from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from uuid import UUID

from django.db import transaction

from apps.core.ids import normalize_ulid
from apps.media.errors import MediaUploadError
from apps.media.imaging import sanitize_image
from apps.media.models import MAX_IMAGE_BYTES, MediaAsset, MediaPurpose, MediaState
from apps.media.storage import MediaStorage

from .cleanup import schedule_pending_cleanup
from .uploads import stage_upload


@dataclass(frozen=True, slots=True)
class ValidatedImportImage:
    content: bytes
    detected_mime: str
    extension: str
    width: int
    height: int
    frame_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ImportedMediaAsset:
    asset_id: str
    purpose: str


def validate_import_image(content: bytes) -> ValidatedImportImage:
    if not isinstance(content, bytes) or not content:
        raise MediaUploadError("media.invalid_image.v1", "图片无法安全解码。")
    if len(content) > MAX_IMAGE_BYTES:
        raise MediaUploadError("media.file_too_large.v1", "单张图片不能超过 2 MiB。")
    sanitized = sanitize_image(BytesIO(content), MediaPurpose.IMPORT)
    if len(sanitized.content) > MAX_IMAGE_BYTES:
        raise MediaUploadError(
            "media.file_too_large.v1", "清洗后的图片不能超过 2 MiB。"
        )
    return ValidatedImportImage(
        content=sanitized.content,
        detected_mime=str(sanitized.detected_mime),
        extension=sanitized.extension,
        width=sanitized.width,
        height=sanitized.height,
        frame_count=sanitized.frame_count,
        sha256=sha256(sanitized.content).hexdigest(),
    )


def create_import_asset(
    *,
    owner_id: UUID,
    article_id: str,
    purpose: MediaPurpose | str,
    original_name: str,
    content: bytes,
    storage: MediaStorage,
    capacity_check: Callable[[], None],
) -> ImportedMediaAsset:
    try:
        normalized_purpose = MediaPurpose(purpose)
    except (TypeError, ValueError):
        raise MediaUploadError("media.purpose_invalid.v1", "图片用途不合法。") from None
    if normalized_purpose not in {MediaPurpose.BODY, MediaPurpose.COVER}:
        raise MediaUploadError("media.purpose_invalid.v1", "图片用途不合法。")
    asset = stage_upload(
        owner_id=owner_id,
        purpose=normalized_purpose,
        original_name=original_name,
        declared_content_type="application/octet-stream",
        chunks=(content,),
        storage=storage,
        capacity_check=capacity_check,
        target_id=normalize_ulid(article_id),
    )
    if asset.state != MediaState.ACTIVE:
        raise MediaUploadError("media.activation_failed.v1", "图片暂时无法使用。")
    return ImportedMediaAsset(asset.id, asset.purpose)


def discard_import_assets(
    *,
    owner_id: UUID,
    asset_ids: tuple[str, ...],
    storage: MediaStorage,
) -> tuple[str, ...]:
    if not isinstance(owner_id, UUID) or not isinstance(asset_ids, tuple):
        raise ValueError("Invalid imported media cleanup request")
    normalized = tuple(dict.fromkeys(normalize_ulid(value) for value in asset_ids))
    if not normalized:
        return ()
    with transaction.atomic():
        assets = list(
            MediaAsset.objects.select_for_update()
            .filter(pk__in=normalized)
            .order_by("id")
        )
        if len(assets) != len(normalized) or any(
            asset.owner_id != owner_id for asset in assets
        ):
            raise ValueError("Imported media cleanup target is invalid")
        removable = tuple(
            asset.id
            for asset in assets
            if not asset.bindings.exists()
            and asset.state in {MediaState.STAGED, MediaState.ACTIVE}
        )
        MediaAsset.objects.filter(pk__in=removable).update(
            state=MediaState.DELETE_PENDING
        )
        schedule_pending_cleanup(removable, storage=storage)
    return removable
