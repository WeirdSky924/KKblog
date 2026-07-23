import re
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import PurePath
from uuid import UUID

from django.db import transaction

from apps.core.ids import is_ulid, new_ulid
from apps.media.errors import MediaUploadError
from apps.media.imaging import sanitize_image
from apps.media.models import MAX_IMAGE_BYTES, MediaAsset, MediaPurpose, MediaState
from apps.media.storage import MediaStorage, StorageLimitExceeded

CapacityCheck = Callable[[], None]
_SAFE_TARGET = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _display_name(value: str) -> str:
    name = PurePath(value.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", name)
    cleaned = "".join(character for character in normalized if character.isprintable())
    return cleaned[:255] or "image"


def _storage_key(
    *,
    owner_id: UUID,
    purpose: MediaPurpose,
    asset_id: str,
    extension: str,
    target_id: str | None,
) -> str:
    if not is_ulid(asset_id):
        raise ValueError("asset_id must be a ULID")
    if purpose == MediaPurpose.LOGO:
        return f"site/brand/{asset_id}.{extension}"
    if purpose == MediaPurpose.FRIEND_LOGO:
        return f"site/friend-links/{asset_id}.{extension}"
    if purpose == MediaPurpose.AVATAR:
        return f"users/{owner_id}/avatar/{asset_id}.{extension}"
    if target_id is None or not _SAFE_TARGET.fullmatch(target_id.upper()):
        raise MediaUploadError("media.target_invalid.v1", "此图片需要有效的归属对象。")
    segment = {
        MediaPurpose.COVER: "cover",
        MediaPurpose.BODY: "body",
        MediaPurpose.COMMENT: "comments",
        MediaPurpose.EVIDENCE: "evidence",
        MediaPurpose.IMPORT: "imports",
    }[purpose]
    return f"users/{owner_id}/articles/{target_id.upper()}/{segment}/{asset_id}.{extension}"


def stage_upload(
    *,
    owner_id: UUID,
    purpose: MediaPurpose | str,
    original_name: str,
    declared_content_type: str,
    chunks: Iterable[bytes],
    storage: MediaStorage,
    capacity_check: CapacityCheck,
    target_id: str | None = None,
) -> MediaAsset:
    if not isinstance(owner_id, UUID):
        raise MediaUploadError("media.owner_invalid.v1", "上传者身份不合法。")
    try:
        normalized_purpose = MediaPurpose(purpose)
    except (TypeError, ValueError):
        raise MediaUploadError("media.purpose_invalid.v1", "图片用途不合法。") from None
    if not callable(capacity_check):
        raise TypeError("capacity_check must be callable")
    del declared_content_type
    capacity_check()

    try:
        raw = storage.stage(chunks, max_bytes=MAX_IMAGE_BYTES)
    except StorageLimitExceeded:
        raise MediaUploadError(
            "media.file_too_large.v1", "单张图片不能超过 2 MiB。"
        ) from None
    try:
        with storage.open_staged(raw) as stream:
            sanitized = sanitize_image(stream, normalized_purpose)
    finally:
        storage.discard(raw)

    try:
        staged = storage.stage([sanitized.content], max_bytes=MAX_IMAGE_BYTES)
    except StorageLimitExceeded:
        raise MediaUploadError(
            "media.file_too_large.v1", "清洗后的图片不能超过 2 MiB。"
        ) from None

    asset_id = new_ulid()
    storage_key = _storage_key(
        owner_id=owner_id,
        purpose=normalized_purpose,
        asset_id=asset_id,
        extension=sanitized.extension,
        target_id=target_id,
    )

    def activate() -> None:
        storage.commit(staged, storage_key)
        updated = MediaAsset.objects.filter(
            pk=asset_id, state=MediaState.STAGED
        ).update(state=MediaState.ACTIVE)
        if updated != 1:
            storage.delete(storage_key)
            raise RuntimeError("Media activation state changed")

    try:
        with transaction.atomic():
            asset = MediaAsset.objects.create(
                id=asset_id,
                owner_id=owner_id,
                purpose=normalized_purpose,
                storage_key=storage_key,
                original_name=_display_name(original_name),
                detected_mime=sanitized.detected_mime,
                size_bytes=staged.size_bytes,
                sha256=staged.sha256,
                width=sanitized.width,
                height=sanitized.height,
                state=MediaState.STAGED,
            )
            transaction.on_commit(activate)
    except Exception:
        storage.discard(staged)
        raise
    asset.refresh_from_db()
    return asset
