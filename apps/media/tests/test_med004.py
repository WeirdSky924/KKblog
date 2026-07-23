from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.urls import reverse
from PIL import Image

from apps.core.ids import new_ulid
from apps.media.models import MediaPurpose, MediaTargetType
from apps.media.services.bindings import BindingInput, bind_assets
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.targets import (
    TargetAccessDecision,
    TargetAccessRequest,
    default_target_access_registry,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 12), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _asset(owner, root: Path, purpose: MediaPurpose, target_id: str | None = None):
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name="delivery.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=target_id,
    )


def _authorize(client, asset_id: str, **headers):
    return client.get(
        reverse("media:internal-authorize"),
        HTTP_X_FORWARDED_URI=f"/_kaj/media/{asset_id}",
        HTTP_X_KAJ_INTERNAL_AUTH="1",
        **headers,
    )


def test_internal_authorize_requires_caddy_marker_and_ignores_spoofed_key(
    client, isolated_media_root: Path
) -> None:
    owner = _account("delivery-marker")
    asset = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)
    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(asset.id, "avatar"),),
    )

    missing_marker = client.get(
        reverse("media:internal-authorize"),
        HTTP_X_FORWARDED_URI=f"/_kaj/media/{asset.id}",
    )
    assert missing_marker.status_code == 404
    authorized = _authorize(client, asset.id, HTTP_X_KAJ_STORAGE_KEY="../../etc/passwd")
    assert authorized.status_code == 200
    assert authorized.headers["X-Kaj-Storage-Key"] == asset.storage_key
    assert authorized.headers["X-Kaj-Cache-Control"].startswith("public,")
    assert authorized.headers["X-Content-Type-Options"] == "nosniff"


def test_unbound_unknown_and_traversal_requests_are_privacy_404(
    client, isolated_media_root: Path
) -> None:
    owner = _account("delivery-unbound")
    asset = _asset(owner, isolated_media_root, MediaPurpose.AVATAR)
    assert _authorize(client, asset.id).status_code == 404
    assert _authorize(client, new_ulid()).status_code == 404
    traversal = client.get(
        reverse("media:internal-authorize"),
        HTTP_X_FORWARDED_URI="/_kaj/media/../../etc/passwd",
        HTTP_X_KAJ_INTERNAL_AUTH="1",
    )
    assert traversal.status_code == 404


@dataclass
class _EvidencePort:
    owner_id: UUID

    def __call__(self, request: TargetAccessRequest) -> TargetAccessDecision:
        allowed = request.actor_id == self.owner_id
        return TargetAccessDecision(True, allowed, allowed, False)


def test_private_delivery_is_no_store_and_rechecks_actor(
    client, isolated_media_root: Path, monkeypatch
) -> None:
    owner = _account("delivery-private")
    other = _account("delivery-other")
    report_id = new_ulid()
    asset = _asset(
        owner, isolated_media_root, MediaPurpose.EVIDENCE, target_id=report_id
    )
    monkeypatch.setitem(
        default_target_access_registry._ports,
        MediaTargetType.REPORT,
        _EvidencePort(owner.id),
    )
    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.REPORT,
        target_id=report_id,
        inputs=(BindingInput(asset.id, "evidence-1"),),
    )

    assert _authorize(client, asset.id).status_code == 404
    _authenticate(client, other)
    assert _authorize(client, asset.id).status_code == 404
    client.cookies.clear()
    _authenticate(client, owner)
    authorized = _authorize(client, asset.id)
    assert authorized.status_code == 200
    assert authorized.headers["X-Kaj-Cache-Control"] == "private, no-store"
    assert authorized.headers["X-Kaj-Public"] == "0"


def test_caddy_contract_strips_internal_headers_and_sets_cache_policy() -> None:
    project_root = Path(__file__).resolve().parents[3]
    contract = (project_root / "docker/caddy/media-delivery.caddy").read_text(
        encoding="utf-8"
    )
    assert "request_header -X-Kaj-Internal-Auth" in contract
    assert 'header_up X-Kaj-Internal-Auth "1"' in contract
    assert "X-Kaj-Cache-Control" in contract
    assert "header Cache-Control" in contract
