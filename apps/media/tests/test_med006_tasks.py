import os
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from PIL import Image

from apps.core.ids import new_ulid
from apps.media.models import MediaPurpose, MediaState, MediaTargetType
from apps.media.services.access import MediaAccessError, authorize_asset_read
from apps.media.services.bindings import BindingInput, bind_assets
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.targets import (
    TargetAccessDecision,
    TargetAccessRegistry,
    TargetAccessRequest,
)
from apps.media.tasks.cleanup import (
    cleanup_staged_media,
    dispatch_pending_media,
    dispatch_staged_media,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 16), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _asset(owner, root: Path, *, purpose=MediaPurpose.AVATAR, target_id=None):
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name="lifecycle.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=target_id,
    )


@dataclass
class _SoftDeletePort:
    owner_id: UUID
    readable: bool = True

    def __call__(self, request: TargetAccessRequest) -> TargetAccessDecision:
        owner = request.actor_id == self.owner_id
        return TargetAccessDecision(True, owner, owner and self.readable, False)


def test_soft_delete_retains_binding_and_file_until_target_purge(
    isolated_media_root: Path,
) -> None:
    owner = _account("soft-delete")
    target_id = new_ulid()
    asset = _asset(
        owner,
        isolated_media_root,
        purpose=MediaPurpose.EVIDENCE,
        target_id=target_id,
    )
    port = _SoftDeletePort(owner.id)
    registry = TargetAccessRegistry()
    registry.register(MediaTargetType.REPORT, port)
    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.REPORT,
        target_id=target_id,
        inputs=(BindingInput(asset.id, "evidence-1"),),
        registry=registry,
    )
    storage = FilesystemMediaStorage(isolated_media_root)

    assert (
        authorize_asset_read(
            actor_id=owner.id, asset_id=asset.id, registry=registry
        ).asset_id
        == asset.id
    )
    port.readable = False
    with pytest.raises(MediaAccessError):
        authorize_asset_read(
            actor_id=owner.id,
            asset_id=asset.id,
            registry=registry,
        )
    asset.refresh_from_db()
    assert asset.state == MediaState.ACTIVE
    assert asset.bindings.filter(target_id=target_id).exists()
    assert storage.exists(asset.storage_key)

    port.readable = True
    assert (
        authorize_asset_read(
            actor_id=owner.id, asset_id=asset.id, registry=registry
        ).asset_id
        == asset.id
    )


def test_staged_expiry_task_is_tracked_and_idempotent(
    isolated_media_root: Path,
) -> None:
    owner = _account("staged-task")
    asset = _asset(owner, isolated_media_root)
    type(asset).objects.filter(pk=asset.id).update(
        created_at=timezone.now() - timedelta(days=2)
    )

    first = cleanup_staged_media.apply(args=(asset.id,), task_id=str(uuid4())).get()
    duplicate = cleanup_staged_media.apply(args=(asset.id,), task_id=str(uuid4())).get()
    asset.refresh_from_db()
    task_run_model = apps.get_model("operations", "TaskRun")
    run = task_run_model.objects.get(task_name="apps.media.cleanup_staged_media")
    assert first["status"] == "deleted"
    assert duplicate["status"] == "already_succeeded"
    assert asset.state == MediaState.DELETED
    assert run.status == "succeeded"
    assert run.attempt == 1


def test_dispatchers_queue_bounded_assets_and_remove_old_parts(
    isolated_media_root: Path, monkeypatch
) -> None:
    owner = _account("cleanup-dispatch")
    pending = _asset(owner, isolated_media_root)
    expired = _asset(owner, isolated_media_root)
    type(pending).objects.filter(pk=pending.id).update(state=MediaState.DELETE_PENDING)
    type(expired).objects.filter(pk=expired.id).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    storage = FilesystemMediaStorage(isolated_media_root)
    staged = storage.stage([b"orphan"], max_bytes=10)
    staged_path = isolated_media_root / ".staging" / f"{staged.token}.part"
    old = timezone.now() - timedelta(days=2)
    os.utime(staged_path, (old.timestamp(), old.timestamp()))
    pending_calls: list[str] = []
    staged_calls: list[str] = []
    monkeypatch.setattr(
        "apps.media.tasks.cleanup.delete_pending_media.delay",
        pending_calls.append,
    )
    monkeypatch.setattr(
        "apps.media.tasks.cleanup.cleanup_staged_media.delay",
        staged_calls.append,
    )

    pending_result = dispatch_pending_media.apply(task_id=str(uuid4())).get()
    staged_result = dispatch_staged_media.apply(task_id=str(uuid4())).get()
    assert pending_result["status"] == "queued"
    assert staged_result["status"] == "queued"
    assert pending_calls == [pending.id]
    assert staged_calls == [expired.id]
    with pytest.raises(FileNotFoundError):
        storage.open_staged(staged)
    task_run_model = apps.get_model("operations", "TaskRun")
    assert task_run_model.objects.filter(status="succeeded").count() == 2
    assert settings.CELERY_BEAT_SCHEDULE["media-delete-pending"]["schedule"] == 60.0
    assert settings.CELERY_BEAT_SCHEDULE["media-cleanup-staged"]["schedule"] == 3_600.0
