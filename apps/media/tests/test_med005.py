from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse
from PIL import Image

from apps.media.models import MediaAsset, MediaPurpose

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


def _image_bytes(format_name: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 18), "#7e2637").save(output, format=format_name)
    return output.getvalue()


def _upload(client, adapter: str, payload: bytes, name: str):
    return client.post(
        reverse("media:upload", kwargs={"adapter": adapter}),
        {"file": SimpleUploadedFile(name, payload)},
    )


def test_upload_adapters_enforce_consumer_permissions_and_purpose(
    client, isolated_media_root: Path
) -> None:
    ordinary = _account("picker-user")
    administrator = _account("picker-admin", administrator=True)

    assert _upload(client, "avatar", _image_bytes(), "avatar.png").status_code == 404
    _authenticate(client, ordinary)
    avatar = _upload(client, "avatar", _image_bytes(), "avatar.png")
    assert avatar.status_code == 201
    avatar_asset = MediaAsset.objects.get(id=avatar.context["asset"].id)
    assert avatar_asset.purpose == MediaPurpose.AVATAR
    assert not avatar_asset.bindings.exists()
    assert avatar.headers["Cache-Control"] == "no-store"

    denied_logo = _upload(client, "site-logo", _image_bytes(), "logo.png")
    denied_friend = _upload(client, "friend-logo", _image_bytes(), "friend.png")
    assert denied_logo.status_code == denied_friend.status_code == 404
    client.cookies.clear()
    _authenticate(client, administrator)
    logo = _upload(client, "site-logo", _image_bytes(), "logo.png")
    wrong_logo_format = _upload(client, "site-logo", _image_bytes("GIF"), "logo.gif")
    friend = _upload(client, "friend-logo", _image_bytes("GIF"), "friend.gif")
    assert logo.status_code == friend.status_code == 201
    assert wrong_logo_format.status_code == 422
    assert logo.context["asset"].purpose == MediaPurpose.LOGO
    assert friend.context["asset"].purpose == MediaPurpose.FRIEND_LOGO


def test_picker_upload_returns_safe_retryable_partial_and_keeps_name(
    client, isolated_media_root: Path
) -> None:
    account = _account("picker-errors")
    _authenticate(client, account)
    response = _upload(client, "avatar", b"not-an-image", "头像-坏图.png")
    assert response.status_code == 422
    body = response.content.decode()
    assert 'data-media-upload-result="error"' in body
    assert "头像-坏图.png" in body
    assert "not-an-image" not in body
    assert response.headers["Cache-Control"] == "no-store"


def test_picker_partial_has_stable_state_track_and_consumer_contract() -> None:
    html = render_to_string(
        "media/partials/picker.html",
        {
            "picker_id": "profile-avatar",
            "adapter": "avatar",
            "input_name": "avatar_asset_id",
            "label": "头像",
        },
    )
    assert 'data-media-picker="avatar"' in html
    assert 'data-media-input-name="avatar_asset_id"' in html
    assert "01 选择" in html
    assert "02 校验" in html
    assert "03 可用" in html
    assert 'aria-live="polite"' in html
    assert 'tabindex="-1"' in html
    assert 'aria-hidden="true"' in html
    assert "data-media-retry" in html
    assert "data-media-remove" in html
    assert reverse("media:upload", kwargs={"adapter": "avatar"}) in html

    project_root = Path(__file__).resolve().parents[3]
    picker_script = (project_root / "static/src/app.js").read_text(encoding="utf-8")
    assert "event.defaultPrevented" in picker_script
    assert "input.disabled || !(file instanceof File)" in picker_script


def test_brand_assets_have_distinct_semantics_dimensions_and_references() -> None:
    project_root = Path(__file__).resolve().parents[3]
    brand_root = project_root / "apps/media/static/media/brand"
    default_cover = brand_root / "default-cover.png"
    unavailable = brand_root / "unavailable-bookmark.png"
    mark = brand_root / "k-mark.svg"

    with Image.open(default_cover) as image:
        assert image.size == (1600, 900)
    with Image.open(unavailable) as image:
        assert image.size == (800, 450)
    assert default_cover.read_bytes() != unavailable.read_bytes()
    assert "<path" in mark.read_text(encoding="utf-8")

    base = (project_root / "templates/base.html").read_text(encoding="utf-8")
    assert "media/brand/k-mark.svg" in base
    assert "data-site-favicon" in base
    assert "media/brand/default-cover.png" in render_to_string(
        "media/brand/default_cover.html"
    )
    assert "media/brand/unavailable-bookmark.png" in render_to_string(
        "media/brand/unavailable_bookmark.html"
    )
