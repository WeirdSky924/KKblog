import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.ids import normalize_ulid
from apps.media.models import MediaAsset, MediaBinding, MediaState, MediaTargetType
from apps.media.storage import (
    FilesystemMediaStorage,
    MediaStorage,
    StorageBoundaryError,
)

logger = logging.getLogger("kaj.media_cleanup")


class CleanupOutcome(StrEnum):
    DELETED = "deleted"
    ALREADY_DELETED = "already_deleted"
    ABSENT = "absent"
    RETAINED = "retained"
    NOT_DUE = "not_due"
    SCHEDULED = "scheduled"


class MediaCleanupRetryable(RuntimeError):
    error_code = "media.file_delete_failed.v1"

    def __init__(self) -> None:
        super().__init__(self.error_code)


@dataclass(frozen=True, slots=True)
class MediaCleanupResult:
    asset_id: str
    outcome: CleanupOutcome


@dataclass(frozen=True, slots=True)
class ReleaseTargetAssetsResult:
    asset_ids: tuple[str, ...]
    pending_asset_ids: tuple[str, ...]
    retained_asset_ids: tuple[str, ...]


def _asset_id(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid media asset ID") from None


def _storage(value: MediaStorage | None) -> MediaStorage:
    candidate = value or FilesystemMediaStorage(settings.MEDIA_ROOT)
    if not callable(getattr(candidate, "delete", None)):
        raise TypeError("storage must implement media deletion")
    return candidate


def delete_pending_asset(
    *, asset_id: str, storage: MediaStorage | None = None
) -> MediaCleanupResult:
    normalized_id = _asset_id(asset_id)
    active_storage = _storage(storage)
    with transaction.atomic():
        asset = MediaAsset.objects.select_for_update().filter(pk=normalized_id).first()
        if asset is None:
            return MediaCleanupResult(normalized_id, CleanupOutcome.ABSENT)
        if asset.state == MediaState.DELETED:
            return MediaCleanupResult(normalized_id, CleanupOutcome.ALREADY_DELETED)
        if asset.state != MediaState.DELETE_PENDING or asset.bindings.exists():
            return MediaCleanupResult(normalized_id, CleanupOutcome.RETAINED)
        try:
            active_storage.delete(asset.storage_key)
        except (OSError, StorageBoundaryError):
            raise MediaCleanupRetryable from None
        asset.mark_deleted()
        asset.save(update_fields=("state", "deleted_at"))
    return MediaCleanupResult(normalized_id, CleanupOutcome.DELETED)


def schedule_pending_cleanup(
    asset_ids: tuple[str, ...], *, storage: MediaStorage | None = None
) -> None:
    normalized_ids = tuple(dict.fromkeys(_asset_id(value) for value in asset_ids))
    if not normalized_ids:
        return

    def cleanup_after_commit() -> None:
        active_storage = _storage(storage)
        for asset_id in normalized_ids:
            try:
                delete_pending_asset(asset_id=asset_id, storage=active_storage)
            except MediaCleanupRetryable:
                logger.error(
                    "Media file deletion deferred asset_id=%s",
                    asset_id,
                )

    transaction.on_commit(cleanup_after_commit)


def release_owner_assets(
    *, owner_id: UUID, storage: MediaStorage | None = None
) -> tuple[str, ...]:
    if not isinstance(owner_id, UUID):
        raise ValueError("Invalid media owner ID")
    with transaction.atomic():
        assets = list(
            MediaAsset.objects.select_for_update()
            .filter(owner_id=owner_id)
            .exclude(state=MediaState.DELETED)
            .order_by("id")
        )
        asset_ids = tuple(asset.id for asset in assets)
        if not asset_ids:
            return ()
        MediaBinding.objects.filter(asset_id__in=asset_ids).delete()
        MediaAsset.objects.filter(
            id__in=asset_ids,
            state__in=(MediaState.STAGED, MediaState.ACTIVE),
        ).update(state=MediaState.DELETE_PENDING)
        schedule_pending_cleanup(asset_ids, storage=storage)
    return asset_ids


def release_target_assets(
    *,
    target_type: MediaTargetType | str,
    target_ids: tuple[str, ...],
    storage: MediaStorage | None = None,
) -> ReleaseTargetAssetsResult:
    try:
        normalized_type = MediaTargetType(target_type)
    except (TypeError, ValueError):
        raise ValueError("Invalid media target type") from None
    if not isinstance(target_ids, tuple) or not 1 <= len(target_ids) <= 10_000:
        raise ValueError("target_ids must contain between 1 and 10000 items")
    normalized_targets = tuple(dict.fromkeys(target_ids))
    if any(
        not isinstance(target_id, str) or not 1 <= len(target_id) <= 128
        for target_id in normalized_targets
    ):
        raise ValueError("Invalid media target ID")

    with transaction.atomic():
        asset_ids = tuple(
            MediaBinding.objects.filter(
                target_type=normalized_type,
                target_id__in=normalized_targets,
            )
            .order_by("asset_id")
            .values_list("asset_id", flat=True)
            .distinct()
        )
        if not asset_ids:
            return ReleaseTargetAssetsResult((), (), ())
        assets = list(
            MediaAsset.objects.select_for_update()
            .filter(pk__in=asset_ids)
            .order_by("id")
        )
        bindings = list(
            MediaBinding.objects.select_for_update()
            .filter(
                target_type=normalized_type,
                target_id__in=normalized_targets,
                asset_id__in=asset_ids,
            )
            .order_by("asset_id", "id")
        )
        MediaBinding.objects.filter(
            id__in=[binding.id for binding in bindings]
        ).delete()
        retained_ids = frozenset(
            MediaBinding.objects.filter(asset_id__in=asset_ids).values_list(
                "asset_id",
                flat=True,
            )
        )
        pending_ids = tuple(
            asset.id
            for asset in assets
            if asset.id not in retained_ids
            and asset.state
            in (MediaState.STAGED, MediaState.ACTIVE, MediaState.DELETE_PENDING)
        )
        MediaAsset.objects.filter(
            id__in=pending_ids,
            state__in=(MediaState.STAGED, MediaState.ACTIVE),
        ).update(state=MediaState.DELETE_PENDING)
        schedule_pending_cleanup(pending_ids, storage=storage)
    return ReleaseTargetAssetsResult(
        tuple(asset.id for asset in assets),
        pending_ids,
        tuple(asset.id for asset in assets if asset.id in retained_ids),
    )


def expire_unbound_asset(
    *,
    asset_id: str,
    now: datetime,
    max_age: timedelta,
    storage: MediaStorage | None = None,
) -> MediaCleanupResult:
    normalized_id = _asset_id(asset_id)
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or not isinstance(max_age, timedelta)
        or max_age <= timedelta(0)
    ):
        raise ValueError("Invalid media expiry window")
    should_delete = False
    with transaction.atomic():
        asset = MediaAsset.objects.select_for_update().filter(pk=normalized_id).first()
        if asset is None:
            return MediaCleanupResult(normalized_id, CleanupOutcome.ABSENT)
        if asset.state == MediaState.DELETED:
            return MediaCleanupResult(normalized_id, CleanupOutcome.ALREADY_DELETED)
        if asset.bindings.exists():
            return MediaCleanupResult(normalized_id, CleanupOutcome.RETAINED)
        if asset.state == MediaState.DELETE_PENDING:
            should_delete = True
        elif asset.state not in (MediaState.STAGED, MediaState.ACTIVE):
            return MediaCleanupResult(normalized_id, CleanupOutcome.RETAINED)
        elif asset.created_at > now - max_age:
            return MediaCleanupResult(normalized_id, CleanupOutcome.NOT_DUE)
        else:
            asset.state = MediaState.DELETE_PENDING
            asset.save(update_fields=("state",))
            should_delete = True
    if not should_delete:
        return MediaCleanupResult(normalized_id, CleanupOutcome.RETAINED)
    if transaction.get_connection().in_atomic_block:
        schedule_pending_cleanup((normalized_id,), storage=storage)
        return MediaCleanupResult(normalized_id, CleanupOutcome.SCHEDULED)
    return delete_pending_asset(asset_id=normalized_id, storage=storage)


def pending_asset_ids(*, batch_size: int) -> tuple[str, ...]:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("Invalid cleanup batch size")
    if not 1 <= batch_size <= 1_000:
        raise ValueError("Invalid cleanup batch size")
    return tuple(
        MediaAsset.objects.filter(state=MediaState.DELETE_PENDING)
        .order_by("created_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )


def expired_unbound_asset_ids(
    *, now: datetime | None = None, max_age: timedelta, batch_size: int
) -> tuple[str, ...]:
    active_now = now or timezone.now()
    if (
        active_now.tzinfo is None
        or not isinstance(max_age, timedelta)
        or max_age <= timedelta(0)
        or isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1_000
    ):
        raise ValueError("Invalid staged media scan")
    return tuple(
        MediaAsset.objects.filter(
            state__in=(MediaState.STAGED, MediaState.ACTIVE),
            created_at__lte=active_now - max_age,
            bindings__isnull=True,
        )
        .order_by("created_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )
