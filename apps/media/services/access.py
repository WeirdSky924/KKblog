import codecs
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.core.ids import is_ulid
from apps.media.models import (
    MAX_KNOWLEDGE_DOCUMENT_BYTES,
    DetectedFormat,
    MediaAsset,
    MediaPurpose,
    MediaState,
)
from apps.media.storage import (
    FilesystemMediaStorage,
    MediaStorage,
    StorageBoundaryError,
)
from apps.media.targets import (
    TargetAccessOperation,
    TargetAccessRegistry,
    TargetAccessRequest,
    default_target_access_registry,
)


class MediaAccessError(LookupError):
    def __init__(self) -> None:
        self.code = "media.not_found.v1"
        super().__init__("未找到请求的媒体。")


class MediaTextReadError(LookupError):
    def __init__(self) -> None:
        self.code = "media.text_unavailable.v1"
        super().__init__("知识文档暂时无法读取。")


@dataclass(frozen=True, slots=True)
class AssetReadAuthorization:
    asset_id: str
    purpose: str
    original_name: str
    storage_key: str
    detected_mime: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    public_immutable: bool
    bound: bool


@dataclass(frozen=True, slots=True)
class AuthorizedTextRead:
    asset_id: str
    original_name: str
    detected_mime: str
    size_bytes: int
    sha256: str
    chunks: Iterator[str]


_TEXT_CHUNK_BYTES = 64 * 1024


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
        if asset.purpose == MediaPurpose.KNOWLEDGE_DOCUMENT:
            raise MediaAccessError
        if actor_id == asset.owner_id:
            return AssetReadAuthorization(
                asset_id=asset.id,
                purpose=asset.purpose,
                original_name=asset.original_name,
                storage_key=asset.storage_key,
                detected_mime=asset.detected_mime,
                size_bytes=asset.size_bytes,
                sha256=asset.sha256,
                width=asset.width,
                height=asset.height,
                public_immutable=False,
                bound=False,
            )
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
                purpose=asset.purpose,
                original_name=asset.original_name,
                storage_key=asset.storage_key,
                detected_mime=asset.detected_mime,
                size_bytes=asset.size_bytes,
                sha256=asset.sha256,
                width=asset.width,
                height=asset.height,
                public_immutable=decision.public_immutable,
                bound=True,
            )
    raise MediaAccessError


def _validate_text_stream(stream, authorization: AssetReadAuthorization) -> None:
    digest = sha256()
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    total = 0
    while True:
        chunk = stream.read(_TEXT_CHUNK_BYTES)
        if not chunk:
            break
        if not isinstance(chunk, bytes) or b"\x00" in chunk:
            raise MediaTextReadError
        total += len(chunk)
        if total > MAX_KNOWLEDGE_DOCUMENT_BYTES:
            raise MediaTextReadError
        digest.update(chunk)
        decoder.decode(chunk, final=False)
    decoder.decode(b"", final=True)
    if total != authorization.size_bytes or digest.hexdigest() != authorization.sha256:
        raise MediaTextReadError
    stream.seek(0)


def _decoded_text_chunks(stream) -> Iterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    while True:
        chunk = stream.read(_TEXT_CHUNK_BYTES)
        if not chunk:
            break
        decoded = decoder.decode(chunk, final=False)
        if decoded:
            yield decoded
    final = decoder.decode(b"", final=True)
    if final:
        yield final


@contextmanager
def _stream_text_authorization(
    authorization: AssetReadAuthorization,
    *,
    storage: MediaStorage | None,
    require_bound: bool,
) -> Iterator[AuthorizedTextRead]:
    if (
        authorization.purpose != MediaPurpose.KNOWLEDGE_DOCUMENT
        or authorization.detected_mime != DetectedFormat.MARKDOWN
        or (require_bound and not authorization.bound)
        or not 1 <= authorization.size_bytes <= MAX_KNOWLEDGE_DOCUMENT_BYTES
    ):
        raise MediaTextReadError
    active_storage = storage or FilesystemMediaStorage(settings.MEDIA_ROOT)
    if not callable(getattr(active_storage, "open_read", None)):
        raise TypeError("storage must implement media reads")
    stream = None
    try:
        stream = active_storage.open_read(authorization.storage_key)
        _validate_text_stream(stream, authorization)
    except MediaTextReadError:
        if stream is not None:
            stream.close()
        raise
    except (FileNotFoundError, OSError, StorageBoundaryError, UnicodeDecodeError):
        if stream is not None:
            stream.close()
        raise MediaTextReadError from None
    try:
        yield AuthorizedTextRead(
            asset_id=authorization.asset_id,
            original_name=authorization.original_name,
            detected_mime=authorization.detected_mime,
            size_bytes=authorization.size_bytes,
            sha256=authorization.sha256,
            chunks=_decoded_text_chunks(stream),
        )
    finally:
        stream.close()


@contextmanager
def stream_authorized_text(
    *,
    actor_id: UUID | None,
    asset_id: str,
    storage: MediaStorage | None = None,
    registry: TargetAccessRegistry = default_target_access_registry,
) -> Iterator[AuthorizedTextRead]:
    authorization = authorize_asset_read(
        actor_id=actor_id,
        asset_id=asset_id,
        registry=registry,
    )
    with _stream_text_authorization(
        authorization,
        storage=storage,
        require_bound=True,
    ) as opened:
        yield opened


@contextmanager
def stream_owned_text_upload(
    *,
    owner_id: UUID,
    asset_id: str,
    storage: MediaStorage | None = None,
) -> Iterator[AuthorizedTextRead]:
    if not isinstance(owner_id, UUID) or not is_ulid(asset_id):
        raise MediaAccessError
    try:
        asset = MediaAsset.objects.get(
            id=asset_id,
            owner_id=owner_id,
            purpose=MediaPurpose.KNOWLEDGE_DOCUMENT,
            detected_mime=DetectedFormat.MARKDOWN,
            state=MediaState.ACTIVE,
            bindings__isnull=True,
        )
    except MediaAsset.DoesNotExist:
        raise MediaAccessError from None
    authorization = AssetReadAuthorization(
        asset_id=asset.id,
        purpose=asset.purpose,
        original_name=asset.original_name,
        storage_key=asset.storage_key,
        detected_mime=asset.detected_mime,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        width=asset.width,
        height=asset.height,
        public_immutable=False,
        bound=False,
    )
    with _stream_text_authorization(
        authorization,
        storage=storage,
        require_bound=False,
    ) as opened:
        yield opened
