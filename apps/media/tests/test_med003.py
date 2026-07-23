from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from django.apps import apps
from PIL import Image

from apps.core.ids import new_ulid
from apps.media.models import MediaPurpose, MediaState, MediaTargetType
from apps.media.services.access import MediaAccessError, authorize_asset_read
from apps.media.services.bindings import (
    BindingInput,
    MediaBindingError,
    bind_assets,
    replace_bindings,
)
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.targets import (
    TargetAccessDecision,
    TargetAccessRegistry,
    TargetAccessRequest,
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
    Image.new("RGB", (12, 12), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _asset(
    owner,
    isolated_media_root: Path,
    purpose: MediaPurpose,
    *,
    target_id: str | None = None,
):
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name="image.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(isolated_media_root),
        capacity_check=lambda: None,
        target_id=target_id,
    )


def test_avatar_binding_enforces_owner_purpose_slot_and_quantity(
    isolated_media_root: Path,
) -> None:
    owner = _account("avatar-owner")
    other = _account("avatar-other")
    first = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)
    second = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)

    created = bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(first.id, "avatar"),),
    )
    assert created[0].asset_id == first.id

    for actor_id, asset_id, slot in (
        (other.id, second.id, "avatar"),
        (owner.id, second.id, "second-avatar"),
    ):
        with pytest.raises(MediaBindingError):
            bind_assets(
                actor_id=actor_id,
                target_type=MediaTargetType.ACCOUNT_PROFILE,
                target_id=str(owner.id),
                inputs=(BindingInput(asset_id, slot),),
            )


def test_replace_binding_cleans_unreferenced_asset_after_commit(
    isolated_media_root: Path,
) -> None:
    owner = _account("replace")
    first = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)
    second = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)
    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(first.id, "avatar"),),
    )

    result = replace_bindings(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(second.id, "avatar"),),
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert result.active_asset_ids == (second.id,)
    assert result.pending_delete_asset_ids == (first.id,)
    assert first.state == MediaState.DELETED
    assert not (isolated_media_root / first.storage_key).exists()
    assert second.state == MediaState.ACTIVE


def test_unbound_or_now_disabled_profile_asset_is_not_readable(
    isolated_media_root: Path,
) -> None:
    owner = _account("read")
    asset = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=None, asset_id=asset.id)

    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(asset.id, "avatar"),),
    )
    public = authorize_asset_read(actor_id=None, asset_id=asset.id)
    assert public.public_immutable is True

    owner.status = owner.Status.DISABLED
    owner.save(update_fields=("status", "updated_at"))
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=None, asset_id=asset.id)


@dataclass
class _PrivateReportPort:
    owner_id: UUID
    exists: bool = True

    def __call__(self, request: TargetAccessRequest) -> TargetAccessDecision:
        return TargetAccessDecision(
            exists=self.exists,
            can_bind=request.actor_id == self.owner_id,
            can_read=request.actor_id == self.owner_id,
            public_immutable=False,
        )


def test_private_evidence_rechecks_registered_target_access(
    isolated_media_root: Path,
) -> None:
    owner = _account("evidence-owner")
    other = _account("evidence-other")
    report_id = new_ulid()
    asset = _asset(
        owner,
        isolated_media_root,
        MediaPurpose.EVIDENCE,
        target_id=report_id,
    )
    port = _PrivateReportPort(owner.id)
    registry = TargetAccessRegistry()
    registry.register(MediaTargetType.REPORT, port)
    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.REPORT,
        target_id=report_id,
        inputs=(BindingInput(asset.id, "evidence-1"),),
        registry=registry,
    )

    authorization = authorize_asset_read(
        actor_id=owner.id, asset_id=asset.id, registry=registry
    )
    assert authorization.public_immutable is False
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=other.id, asset_id=asset.id, registry=registry)

    port.exists = False
    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=owner.id, asset_id=asset.id, registry=registry)


def test_evidence_quantity_limit_is_three(isolated_media_root: Path) -> None:
    owner = _account("evidence-limit")
    report_id = new_ulid()
    assets = [
        _asset(
            owner,
            isolated_media_root,
            MediaPurpose.EVIDENCE,
            target_id=report_id,
        )
        for _ in range(4)
    ]
    registry = TargetAccessRegistry()
    registry.register(MediaTargetType.REPORT, _PrivateReportPort(owner.id))
    with pytest.raises(MediaBindingError) as captured:
        bind_assets(
            actor_id=owner.id,
            target_type=MediaTargetType.REPORT,
            target_id=report_id,
            inputs=tuple(
                BindingInput(asset.id, f"evidence-{index}")
                for index, asset in enumerate(assets, start=1)
            ),
            registry=registry,
        )
    assert captured.value.code == "media.binding_limit_exceeded.v1"
