from dataclasses import dataclass
from hashlib import sha256

from apps.core.ids import normalize_ulid
from apps.media.models import MediaAsset, MediaBinding, MediaState, MediaTargetType
from apps.media.storage import MediaStorage

_EXTENSIONS = {
    "application/vnd.rar": "rar",
    "application/x-7z-compressed": "7z",
    "application/zip": "zip",
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "text/markdown": "md",
    "text/plain": "txt",
}


class MediaExportError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class ExportMediaDescriptor:
    asset_id: str
    purpose: str
    slot: str
    detected_mime: str
    extension: str
    size_bytes: int
    sha256: str


def _revision_ids(values) -> tuple[str, ...]:
    if values is None or isinstance(values, str | bytes):
        raise MediaExportError("exchange.export_media_invalid.v1", "导出媒体选择无效。")
    try:
        return tuple(dict.fromkeys(normalize_ulid(value) for value in values))
    except (TypeError, ValueError):
        raise MediaExportError(
            "exchange.export_media_invalid.v1", "导出媒体选择无效。"
        ) from None


def export_revision_media(
    *, revision_ids
) -> dict[str, tuple[ExportMediaDescriptor, ...]]:
    identities = _revision_ids(revision_ids)
    result: dict[str, list[ExportMediaDescriptor]] = {
        revision_id: [] for revision_id in identities
    }
    if not identities:
        return {}
    bindings = (
        MediaBinding.objects.select_related("asset")
        .filter(
            target_type=MediaTargetType.ARTICLE_REVISION,
            target_id__in=identities,
        )
        .order_by("target_id", "slot", "asset_id")
    )
    for binding in bindings:
        asset = binding.asset
        extension = _EXTENSIONS.get(asset.detected_mime)
        if asset.state != MediaState.ACTIVE or extension is None:
            raise MediaExportError(
                "exchange.export_media_unavailable.v1", "导出媒体不可用。"
            )
        result[binding.target_id].append(
            ExportMediaDescriptor(
                asset_id=asset.id,
                purpose=asset.purpose,
                slot=binding.slot,
                detected_mime=asset.detected_mime,
                extension=extension,
                size_bytes=asset.size_bytes,
                sha256=asset.sha256,
            )
        )
    return {revision_id: tuple(items) for revision_id, items in result.items()}


def read_export_media(*, asset_id: str, storage: MediaStorage) -> bytes:
    if not callable(getattr(storage, "read", None)):
        raise TypeError("Export media storage is required")
    try:
        identity = normalize_ulid(asset_id)
        asset = MediaAsset.objects.get(pk=identity, state=MediaState.ACTIVE)
    except (TypeError, ValueError, MediaAsset.DoesNotExist):
        raise MediaExportError(
            "exchange.export_media_unavailable.v1", "导出媒体不可用。"
        ) from None
    try:
        content = storage.read(asset.storage_key)
    except (FileNotFoundError, OSError):
        raise MediaExportError(
            "exchange.export_media_missing.v1", "导出媒体文件不存在。"
        ) from None
    if len(content) != asset.size_bytes or sha256(content).hexdigest() != asset.sha256:
        raise MediaExportError(
            "exchange.export_media_corrupt.v1", "导出媒体文件校验失败。"
        )
    return content
