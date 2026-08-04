import re
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import PurePath
from uuid import UUID
from zipfile import is_zipfile

from django.db import transaction

from apps.core.ids import is_ulid, new_ulid
from apps.media.errors import MediaUploadError
from apps.media.imaging import sanitize_image
from apps.media.models import (
    MAX_ATTACHMENT_BYTES,
    MAX_IMAGE_BYTES,
    DetectedFormat,
    MediaAsset,
    MediaPurpose,
    MediaState,
)
from apps.media.storage import MediaStorage, StorageLimitExceeded

CapacityCheck = Callable[[], None]
_SAFE_TARGET = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _display_name(value: str, *, fallback: str = "image") -> str:
    name = PurePath(value.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", name)
    cleaned = "".join(character for character in normalized if character.isprintable())
    return cleaned[:255] or fallback


def _detect_attachment(stream, original_name: str) -> tuple[DetectedFormat, str]:
    name = _display_name(original_name, fallback="attachment")
    extension = PurePath(name).suffix.casefold().lstrip(".")
    allowed = {"zip", "7z", "rar", "md", "txt"}
    if extension not in allowed:
        raise MediaUploadError(
            "media.format_not_allowed.v1",
            "附件仅支持 ZIP、7z、RAR、MD 和 TXT 格式。",
        )
    header = stream.read(8)
    stream.seek(0)
    if extension == "zip":
        if header[:4] not in {
            b"PK\x03\x04",
            b"PK\x05\x06",
            b"PK\x07\x08",
        } or not is_zipfile(stream):
            raise MediaUploadError(
                "media.invalid_attachment.v1", "ZIP 文件内容无法验证。"
            )
        stream.seek(0)
        return DetectedFormat.ZIP, extension
    if extension == "7z":
        if header[:6] != b"7z\xbc\xaf\x27\x1c":
            raise MediaUploadError(
                "media.invalid_attachment.v1", "7z 文件内容无法验证。"
            )
        return DetectedFormat.SEVEN_Z, extension
    if extension == "rar":
        if header[:7] != b"Rar!\x1a\x07\x00" and header != b"Rar!\x1a\x07\x01\x00":
            raise MediaUploadError(
                "media.invalid_attachment.v1", "RAR 文件内容无法验证。"
            )
        return DetectedFormat.RAR, extension
    content = stream.read()
    if b"\x00" in content:
        raise MediaUploadError(
            "media.invalid_attachment.v1", "文本附件必须是可读文本。"
        )
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        raise MediaUploadError(
            "media.invalid_attachment.v1", "文本附件必须使用 UTF-8 编码。"
        ) from None
    return (
        DetectedFormat.MARKDOWN if extension == "md" else DetectedFormat.TEXT,
        extension,
    )


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
    if purpose == MediaPurpose.COMMENT and target_id == "site":
        return f"users/{owner_id}/guestbook/comments/{asset_id}.{extension}"
    if target_id is None or not _SAFE_TARGET.fullmatch(target_id.upper()):
        raise MediaUploadError("media.target_invalid.v1", "此媒体需要有效的归属对象。")
    segment = {
        MediaPurpose.COVER: "cover",
        MediaPurpose.BODY: "body",
        MediaPurpose.COMMENT: "comments",
        MediaPurpose.EVIDENCE: "evidence",
        MediaPurpose.IMPORT: "imports",
        MediaPurpose.ATTACHMENT: "attachments",
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

    max_bytes = (
        MAX_ATTACHMENT_BYTES
        if normalized_purpose == MediaPurpose.ATTACHMENT
        else MAX_IMAGE_BYTES
    )
    try:
        raw = storage.stage(chunks, max_bytes=max_bytes)
    except StorageLimitExceeded:
        raise MediaUploadError(
            "media.file_too_large.v1",
            "附件不能超过 10 MiB。"
            if normalized_purpose == MediaPurpose.ATTACHMENT
            else "单张图片不能超过 2 MiB。",
        ) from None
    if normalized_purpose == MediaPurpose.ATTACHMENT:
        try:
            with storage.open_staged(raw) as stream:
                detected, extension = _detect_attachment(stream, original_name)
        except Exception:
            storage.discard(raw)
            raise
        staged = raw
        width = height = None
    else:
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
        detected = sanitized.detected_mime
        extension = sanitized.extension
        width = sanitized.width
        height = sanitized.height

    asset_id = new_ulid()
    try:
        storage_key = _storage_key(
            owner_id=owner_id,
            purpose=normalized_purpose,
            asset_id=asset_id,
            extension=extension,
            target_id=target_id,
        )
    except Exception:
        storage.discard(staged)
        raise

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
                original_name=_display_name(
                    original_name,
                    fallback="attachment"
                    if normalized_purpose == MediaPurpose.ATTACHMENT
                    else "image",
                ),
                detected_mime=detected,
                size_bytes=staged.size_bytes,
                sha256=staged.sha256,
                width=width,
                height=height,
                state=MediaState.STAGED,
            )
            transaction.on_commit(activate)
    except Exception:
        storage.discard(staged)
        raise
    asset.refresh_from_db()
    return asset
