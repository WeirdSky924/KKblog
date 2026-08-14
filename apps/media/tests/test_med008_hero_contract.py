from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from PIL import Image

from apps.media.models import (
    MAX_HERO_VIDEO_BYTES,
    MAX_IMAGE_BYTES,
    DetectedFormat,
    MediaAsset,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)
from apps.media.services.access import authorize_asset_read
from apps.media.services.bindings import BindingInput, replace_bindings
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.targets import (
    TargetAccessDecision,
    TargetAccessRegistry,
    TargetAccessRequest,
)

pytestmark = pytest.mark.django_db(transaction=True)


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


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (48, 32), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _hero_image(root: Path, owner, name: str) -> MediaAsset:
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.HERO,
        original_name=name,
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
    )


def test_database_keeps_image_limit_and_allows_larger_hero_video() -> None:
    owner = _account("hero-constraint")
    values = {
        "owner": owner,
        "purpose": MediaPurpose.HERO,
        "storage_key": "site/hero/01KZR000000000000000000001.mp4",
        "original_name": "hero.mp4",
        "detected_mime": DetectedFormat.MP4,
        "sha256": "a" * 64,
        "width": 1280,
        "height": 720,
        "state": MediaState.ACTIVE,
    }
    MediaAsset.objects.create(size_bytes=MAX_HERO_VIDEO_BYTES, **values)
    with pytest.raises(IntegrityError), transaction.atomic():
        MediaAsset.objects.create(
            size_bytes=MAX_HERO_VIDEO_BYTES + 1,
            **{**values, "storage_key": "site/hero/01KZR000000000000000000002.mp4"},
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        MediaAsset.objects.create(
            size_bytes=MAX_IMAGE_BYTES + 1,
            **{
                **values,
                "storage_key": "site/hero/01KZR000000000000000000003.png",
                "detected_mime": DetectedFormat.PNG,
            },
        )


@dataclass(frozen=True)
class _SitePort:
    administrator_id: UUID

    def __call__(self, request: TargetAccessRequest) -> TargetAccessDecision:
        return TargetAccessDecision(
            exists=request.target_id == "site",
            can_bind=request.actor_id == self.administrator_id,
            can_read=request.target_id == "site",
            public_immutable=True,
        )


def test_site_hero_binding_replaces_old_asset_and_is_publicly_readable(
    isolated_media_root: Path,
) -> None:
    administrator = _account("hero-binding")
    first = _hero_image(isolated_media_root, administrator, "first.png")
    second = _hero_image(isolated_media_root, administrator, "second.png")
    registry = TargetAccessRegistry()
    registry.register(MediaTargetType.SITE_BRAND, _SitePort(administrator.id))

    for asset in (first, second):
        replace_bindings(
            actor_id=administrator.id,
            target_type=MediaTargetType.SITE_BRAND,
            target_id="site",
            inputs=(BindingInput(asset.id, "hero"),),
            purpose=MediaPurpose.HERO,
            registry=registry,
        )

    first.refresh_from_db()
    assert first.state == MediaState.DELETED
    assert not (isolated_media_root / first.storage_key).exists()
    readable = authorize_asset_read(
        actor_id=None,
        asset_id=second.id,
        registry=registry,
    )
    assert readable.public_immutable is True
    assert readable.detected_mime == DetectedFormat.PNG


def test_site_hero_upload_adapter_is_administrator_only(
    client,
    isolated_media_root: Path,
) -> None:
    ordinary = _account("hero-ordinary")
    administrator = _account("hero-admin", administrator=True)
    upload_url = reverse("media:upload", kwargs={"adapter": "site-hero"})

    _authenticate(client, ordinary)
    denied = client.post(
        upload_url,
        {"file": SimpleUploadedFile("hero.png", _png(), "image/png")},
    )
    assert denied.status_code == 404

    client.cookies.clear()
    _authenticate(client, administrator)
    accepted = client.post(
        upload_url,
        {"file": SimpleUploadedFile("hero.png", _png(), "image/png")},
    )
    assert accepted.status_code == 201
    assert accepted.context["asset"].purpose == MediaPurpose.HERO
