import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from celery.exceptions import Retry
from django.apps import apps
from django.db import connections, transaction
from PIL import Image

from apps.media.models import MediaPurpose, MediaState, MediaTargetType
from apps.media.services.bindings import (
    BindingInput,
    MediaBindingError,
    replace_bindings,
)
from apps.media.services.cleanup import (
    CleanupOutcome,
    MediaCleanupRetryable,
    delete_pending_asset,
    expire_unbound_asset,
)
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.tasks.cleanup import delete_pending_media

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)


def _account(label: str, *, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        role_model = apps.get_model("accounts", "RoleAssignment")
        role_model.objects.create(account=account, role="AUTHOR")
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 18), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _asset(owner, root: Path):
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.AVATAR,
        original_name="cleanup.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
    )


def _bind(owner, asset_id: str) -> None:
    replace_bindings(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(asset_id, "avatar"),),
        purpose=MediaPurpose.AVATAR,
    )


def test_binding_replacement_deletes_only_after_outer_commit_and_not_rollback(
    isolated_media_root: Path,
) -> None:
    owner = _account("cleanup-order")
    first = _asset(owner, isolated_media_root)
    second = _asset(owner, isolated_media_root)
    _bind(owner, first.id)
    storage = FilesystemMediaStorage(isolated_media_root)

    with pytest.raises(RuntimeError), transaction.atomic():
        replace_bindings(
            actor_id=owner.id,
            target_type=MediaTargetType.ACCOUNT_PROFILE,
            target_id=str(owner.id),
            inputs=(BindingInput(second.id, "avatar"),),
            storage=storage,
        )
        first.refresh_from_db()
        assert first.state == MediaState.DELETE_PENDING
        assert storage.exists(first.storage_key)
        raise RuntimeError("rollback before commit")

    first.refresh_from_db()
    assert first.state == MediaState.ACTIVE
    assert first.bindings.filter(slot="avatar").exists()
    assert storage.exists(first.storage_key)

    with transaction.atomic():
        result = replace_bindings(
            actor_id=owner.id,
            target_type=MediaTargetType.ACCOUNT_PROFILE,
            target_id=str(owner.id),
            inputs=(BindingInput(second.id, "avatar"),),
            storage=storage,
        )
        first.refresh_from_db()
        assert first.state == MediaState.DELETE_PENDING
        assert storage.exists(first.storage_key)

    first.refresh_from_db()
    assert result.pending_delete_asset_ids == (first.id,)
    assert first.state == MediaState.DELETED
    assert first.deleted_at is not None
    assert not storage.exists(first.storage_key)


class _FailingStorage:
    def delete(self, storage_key: str) -> bool:
        del storage_key
        raise OSError("private filesystem detail")


class _ProcessCrash(BaseException):
    pass


class _CrashAfterDeleteStorage:
    def __init__(self, storage: FilesystemMediaStorage) -> None:
        self.storage = storage

    def delete(self, storage_key: str) -> bool:
        self.storage.delete(storage_key)
        raise _ProcessCrash


def test_delete_failure_stays_pending_and_missing_file_is_idempotent(
    isolated_media_root: Path,
) -> None:
    owner = _account("cleanup-retry")
    asset = _asset(owner, isolated_media_root)
    type(asset).objects.filter(pk=asset.id).update(state=MediaState.DELETE_PENDING)

    with pytest.raises(MediaCleanupRetryable):
        delete_pending_asset(asset_id=asset.id, storage=_FailingStorage())
    asset.refresh_from_db()
    assert asset.state == MediaState.DELETE_PENDING

    storage = FilesystemMediaStorage(isolated_media_root)
    storage.delete(asset.storage_key)
    first = delete_pending_asset(asset_id=asset.id, storage=storage)
    deleted_at = type(asset).objects.get(pk=asset.id).deleted_at
    second = delete_pending_asset(asset_id=asset.id, storage=storage)
    assert first.outcome == CleanupOutcome.DELETED
    assert second.outcome == CleanupOutcome.ALREADY_DELETED
    assert type(asset).objects.get(pk=asset.id).deleted_at == deleted_at


def test_process_crash_after_file_delete_recovers_from_missing_file(
    isolated_media_root: Path,
) -> None:
    owner = _account("cleanup-hard-crash")
    asset = _asset(owner, isolated_media_root)
    type(asset).objects.filter(pk=asset.id).update(state=MediaState.DELETE_PENDING)
    storage = FilesystemMediaStorage(isolated_media_root)

    with pytest.raises(_ProcessCrash):
        delete_pending_asset(
            asset_id=asset.id,
            storage=_CrashAfterDeleteStorage(storage),
        )
    asset.refresh_from_db()
    assert asset.state == MediaState.DELETE_PENDING
    assert not storage.exists(asset.storage_key)

    result = delete_pending_asset(asset_id=asset.id, storage=storage)
    asset.refresh_from_db()
    assert result.outcome == CleanupOutcome.DELETED
    assert asset.state == MediaState.DELETED


def test_expiry_claims_only_old_unbound_assets_and_cleans_orphan_staging(
    isolated_media_root: Path,
) -> None:
    owner = _account("cleanup-expiry")
    expired = _asset(owner, isolated_media_root)
    bound = _asset(owner, isolated_media_root)
    recent = _asset(owner, isolated_media_root)
    _bind(owner, bound.id)
    type(expired).objects.filter(id__in=(expired.id, bound.id)).update(
        created_at=NOW - timedelta(days=2)
    )
    type(recent).objects.filter(pk=recent.id).update(created_at=NOW)
    storage = FilesystemMediaStorage(isolated_media_root)

    removed = expire_unbound_asset(
        asset_id=expired.id,
        now=NOW,
        max_age=timedelta(days=1),
        storage=storage,
    )
    retained = expire_unbound_asset(
        asset_id=bound.id,
        now=NOW,
        max_age=timedelta(days=1),
        storage=storage,
    )
    not_due = expire_unbound_asset(
        asset_id=recent.id,
        now=NOW,
        max_age=timedelta(days=1),
        storage=storage,
    )
    assert removed.outcome == CleanupOutcome.DELETED
    assert retained.outcome == CleanupOutcome.RETAINED
    assert not_due.outcome == CleanupOutcome.NOT_DUE

    old_part = storage.stage([b"old"], max_bytes=10)
    recent_part = storage.stage([b"recent"], max_bytes=10)
    old_path = isolated_media_root / ".staging" / f"{old_part.token}.part"
    os.utime(old_path, (NOW.timestamp() - 3600, NOW.timestamp() - 3600))
    assert storage.discard_staged_before(NOW - timedelta(minutes=30)) == 1
    with pytest.raises(FileNotFoundError):
        storage.open_staged(old_part)
    with storage.open_staged(recent_part) as stream:
        assert stream.read() == b"recent"


def test_two_workers_and_tracked_task_delete_once(
    isolated_media_root: Path,
) -> None:
    owner = _account("cleanup-workers")
    asset = _asset(owner, isolated_media_root)
    type(asset).objects.filter(pk=asset.id).update(state=MediaState.DELETE_PENDING)

    def worker() -> CleanupOutcome:
        connections.close_all()
        try:
            result = delete_pending_asset(
                asset_id=asset.id,
                storage=FilesystemMediaStorage(isolated_media_root),
            )
            return result.outcome
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: worker(), range(2)))
    assert sorted(outcomes) == sorted(
        (CleanupOutcome.DELETED, CleanupOutcome.ALREADY_DELETED)
    )

    another = _asset(owner, isolated_media_root)
    type(another).objects.filter(pk=another.id).update(state=MediaState.DELETE_PENDING)
    task_id = str(uuid4())
    first = delete_pending_media.apply(args=(another.id,), task_id=task_id).get()
    duplicate = delete_pending_media.apply(
        args=(another.id,), task_id=str(uuid4())
    ).get()
    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.media.delete_pending_media")
    assert first["status"] == "deleted"
    assert duplicate["status"] == "already_succeeded"
    assert run.status == "succeeded"
    assert run.attempt == 1


def test_concurrent_binding_replacement_keeps_one_live_slot(
    isolated_media_root: Path,
) -> None:
    owner = _account("cleanup-concurrent-replace")
    original = _asset(owner, isolated_media_root)
    candidates = (
        _asset(owner, isolated_media_root),
        _asset(owner, isolated_media_root),
    )
    _bind(owner, original.id)

    def worker(asset_id: str) -> str:
        connections.close_all()
        try:
            replace_bindings(
                actor_id=owner.id,
                target_type=MediaTargetType.ACCOUNT_PROFILE,
                target_id=str(owner.id),
                inputs=(BindingInput(asset_id, "avatar"),),
                storage=FilesystemMediaStorage(isolated_media_root),
            )
        except MediaBindingError:
            return "rejected"
        finally:
            connections.close_all()
        return "replaced"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, (asset.id for asset in candidates)))
    binding_model = apps.get_model("media", "MediaBinding")
    bindings = list(
        binding_model.objects.filter(
            target_type=MediaTargetType.ACCOUNT_PROFILE,
            target_id=str(owner.id),
            slot="avatar",
        )
    )
    original.refresh_from_db()
    assert outcomes.count("replaced") == 1
    assert len(bindings) == 1
    assert bindings[0].asset_id in {asset.id for asset in candidates}
    assert bindings[0].asset.state == MediaState.ACTIVE
    assert original.state == MediaState.DELETED
    assert not FilesystemMediaStorage(isolated_media_root).exists(original.storage_key)


def test_tracked_delete_failure_records_safe_retry(
    isolated_media_root: Path, monkeypatch
) -> None:
    owner = _account("cleanup-task-retry")
    asset = _asset(owner, isolated_media_root)
    type(asset).objects.filter(pk=asset.id).update(state=MediaState.DELETE_PENDING)
    monkeypatch.setattr("apps.media.tasks.cleanup._storage", lambda: _FailingStorage())

    with pytest.raises(Retry):
        delete_pending_media.apply(
            args=(asset.id,), task_id=str(uuid4()), throw=True
        ).get()
    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.media.delete_pending_media")
    asset.refresh_from_db()
    assert run.status == "retry_wait"
    assert run.last_error_code == "media.file_delete_failed.v1"
    assert "private" not in str(run.last_error_code)
    assert asset.state == MediaState.DELETE_PENDING
