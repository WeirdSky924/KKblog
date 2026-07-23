from datetime import timedelta
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.ids import normalize_ulid
from apps.media.services.cleanup import (
    MediaCleanupRetryable,
    delete_pending_asset,
    expire_unbound_asset,
    expired_unbound_asset_ids,
    pending_asset_ids,
)
from apps.media.storage import FilesystemMediaStorage
from apps.operations.public import (
    RetryableTaskError,
    StartOutcome,
    execute_celery_entry,
)


def _storage():
    return FilesystemMediaStorage(settings.MEDIA_ROOT)


def _asset_business_object(asset_id: str) -> str:
    return f"asset:{normalize_ulid(asset_id)}"


def _asset_from_business_object(value: str) -> str:
    prefix, separator, asset_id = value.partition(":")
    if prefix != "asset" or separator != ":":
        raise ValueError("Invalid media cleanup business object")
    return normalize_ulid(asset_id)


def _delete_service(business_object: str) -> str:
    asset_id = _asset_from_business_object(business_object)
    try:
        result = delete_pending_asset(asset_id=asset_id, storage=_storage())
    except MediaCleanupRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"asset:{asset_id}:{result.outcome.value}"


def _expiry_service(business_object: str) -> str:
    asset_id = _asset_from_business_object(business_object)
    max_age = timedelta(seconds=settings.MEDIA_STAGED_EXPIRY_SECONDS)
    try:
        result = expire_unbound_asset(
            asset_id=asset_id,
            now=timezone.now(),
            max_age=max_age,
            storage=_storage(),
        )
    except MediaCleanupRetryable as exc:
        raise RetryableTaskError(exc.error_code) from None
    return f"asset:{asset_id}:{result.outcome.value}"


def _task_response(result) -> dict[str, str]:
    if result.outcome == StartOutcome.ALREADY_SUCCEEDED:
        status = "already_succeeded"
    elif result.result_ref.startswith("queued:"):
        status = "queued"
    else:
        status = result.result_ref.rsplit(":", 1)[-1] if result.result_ref else "ok"
    return {"status": status}


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.media.delete_pending_media",
)
def delete_pending_media(self, asset_id: str) -> dict[str, str]:
    normalized_id = normalize_ulid(asset_id)
    result = execute_celery_entry(
        self,
        task_name="apps.media.delete_pending_media",
        business_object=_asset_business_object(normalized_id),
        idempotency_key=f"asset:{normalized_id}:delete",
        service=_delete_service,
    )
    return _task_response(result)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.media.cleanup_staged_media",
)
def cleanup_staged_media(self, asset_id: str) -> dict[str, str]:
    normalized_id = normalize_ulid(asset_id)
    result = execute_celery_entry(
        self,
        task_name="apps.media.cleanup_staged_media",
        business_object=_asset_business_object(normalized_id),
        idempotency_key=f"asset:{normalized_id}:staged-expiry",
        service=_expiry_service,
    )
    return _task_response(result)


def _request_id(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid media dispatcher request ID") from None


def _dispatch_pending_service(business_object: str) -> str:
    del business_object
    ids = pending_asset_ids(batch_size=settings.MEDIA_CLEANUP_BATCH_SIZE)
    for asset_id in ids:
        delete_pending_media.delay(asset_id)
    return f"queued:{len(ids)}"


def _dispatch_staged_service(business_object: str) -> str:
    del business_object
    max_age = timedelta(seconds=settings.MEDIA_STAGED_EXPIRY_SECONDS)
    now = timezone.now()
    ids = expired_unbound_asset_ids(
        now=now,
        max_age=max_age,
        batch_size=settings.MEDIA_CLEANUP_BATCH_SIZE,
    )
    for asset_id in ids:
        cleanup_staged_media.delay(asset_id)
    removed_parts = _storage().discard_staged_before(now - max_age)
    return f"queued:{len(ids)}:parts:{removed_parts}"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.media.dispatch_pending_media",
)
def dispatch_pending_media(self) -> dict[str, str]:
    request_id = _request_id(self)
    result = execute_celery_entry(
        self,
        task_name="apps.media.dispatch_pending_media",
        business_object=f"media-dispatch:{request_id}",
        idempotency_key=f"media-delete-dispatch:{request_id}",
        service=_dispatch_pending_service,
    )
    return _task_response(result)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.media.dispatch_staged_media",
)
def dispatch_staged_media(self) -> dict[str, str]:
    request_id = _request_id(self)
    result = execute_celery_entry(
        self,
        task_name="apps.media.dispatch_staged_media",
        business_object=f"media-dispatch:{request_id}",
        idempotency_key=f"media-staged-dispatch:{request_id}",
        service=_dispatch_staged_service,
    )
    return _task_response(result)
