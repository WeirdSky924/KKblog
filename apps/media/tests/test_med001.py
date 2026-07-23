from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.ids import new_ulid
from apps.media.models import (
    DetectedFormat,
    MediaAsset,
    MediaBinding,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)
from apps.media.storage.filesystem import FilesystemMediaStorage
from apps.media.storage.port import StorageBoundaryError
from apps.media.targets import validate_binding_target

pytestmark = pytest.mark.django_db(transaction=True)


def _owner():
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"media-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _asset(owner, **overrides) -> MediaAsset:
    values = {
        "owner": owner,
        "purpose": MediaPurpose.AVATAR,
        "storage_key": f"users/{owner.id}/avatar/{new_ulid()}.png",
        "original_name": "avatar.png",
        "detected_mime": DetectedFormat.PNG,
        "size_bytes": 128,
        "sha256": "a" * 64,
        "width": 32,
        "height": 32,
        "state": MediaState.STAGED,
    }
    values.update(overrides)
    return MediaAsset.objects.create(**values)


def test_asset_persists_only_controlled_relative_metadata() -> None:
    owner = _owner()
    asset = _asset(owner)
    asset.refresh_from_db()

    assert len(asset.id) == 26
    assert not Path(asset.storage_key).is_absolute()
    assert ".." not in Path(asset.storage_key).parts
    assert owner.email not in asset.storage_key
    assert asset.size_bytes == 128
    assert not hasattr(asset, "content")
    assert not hasattr(asset, "absolute_path")


@pytest.mark.parametrize("size", [0, 2 * 1024 * 1024 + 1])
def test_asset_size_constraint_is_enforced_by_database(size: int) -> None:
    owner = _owner()
    with pytest.raises(IntegrityError), transaction.atomic():
        _asset(owner, size_bytes=size)


@pytest.mark.parametrize(
    "storage_key",
    [
        "/etc/passwd",
        "../outside.png",
        "users/id/../../outside.png",
        r"users\id\outside.png",
    ],
)
def test_asset_rejects_uncontrolled_storage_keys(storage_key: str) -> None:
    owner = _owner()
    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        _asset(owner, storage_key=storage_key)


def test_binding_target_and_slot_are_unique_and_registered() -> None:
    owner = _owner()
    first = _asset(owner)
    second = _asset(owner, storage_key=f"users/{owner.id}/avatar/{new_ulid()}.png")

    validate_binding_target(MediaPurpose.AVATAR, MediaTargetType.ACCOUNT_PROFILE)
    MediaBinding.objects.bind(
        asset=first,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        slot="avatar",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        MediaBinding.objects.bind(
            asset=second,
            target_type=MediaTargetType.ACCOUNT_PROFILE,
            target_id=str(owner.id),
            slot="avatar",
        )
    with pytest.raises(ValidationError):
        validate_binding_target(MediaPurpose.AVATAR, "arbitrary-target")
    with pytest.raises(ValidationError):
        validate_binding_target(MediaPurpose.EVIDENCE, MediaTargetType.ACCOUNT_PROFILE)


def test_filesystem_storage_reads_and_deletes_inside_root(
    isolated_media_root: Path,
) -> None:
    storage = FilesystemMediaStorage(isolated_media_root)
    key = f"users/{uuid4()}/avatar/{new_ulid()}.png"

    storage.write(key, [b"safe", b"-bytes"])
    assert storage.read(key) == b"safe-bytes"
    assert storage.exists(key)
    assert storage.delete(key) is True
    assert storage.delete(key) is False


def test_filesystem_storage_rejects_traversal_and_symlink_escape(
    isolated_media_root: Path, tmp_path: Path
) -> None:
    storage = FilesystemMediaStorage(isolated_media_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (isolated_media_root / "escape").symlink_to(outside, target_is_directory=True)

    for key in ("../outside", "/etc/passwd", "escape/file.png"):
        with pytest.raises(StorageBoundaryError):
            storage.write(key, [b"blocked"])
    assert list(outside.iterdir()) == []
