import base64
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Account, RoleAssignment
from apps.administration.forms.site_settings import SiteConfigurationForm
from apps.core.ids import new_ulid
from apps.media.models import (
    DetectedFormat,
    MediaAsset,
    MediaBinding,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)
from apps.media.storage import FilesystemMediaStorage
from apps.navigation.models import SiteConfiguration
from apps.navigation.public import SiteContentCommandError, update_site_configuration
from apps.navigation.queries import public_site_configuration
from config.navigation_integrations import configure_navigation_integrations

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _configure_integrations() -> None:
    configure_navigation_integrations()


def _account(label: str, *, administrator: bool = False) -> Account:
    account = Account.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        RoleAssignment.objects.bulk_create(
            (
                RoleAssignment(account=account, role=RoleAssignment.Role.AUTHOR),
                RoleAssignment(
                    account=account,
                    role=RoleAssignment.Role.ADMINISTRATOR,
                ),
            )
        )
    return account


def _png() -> bytes:
    from io import BytesIO

    output = BytesIO()
    Image.new("RGB", (96, 54), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _video() -> bytes:
    fixture = (
        Path(__file__).parents[2]
        / "media"
        / "tests"
        / "fixtures"
        / "hero-sample.webm.b64"
    )
    return base64.b64decode(b"".join(fixture.read_bytes().split()), validate=True)


def _asset(root: Path, owner: Account, *, video: bool = False) -> MediaAsset:
    asset_id = new_ulid()
    payload = _video() if video else _png()
    extension = "webm" if video else "png"
    storage_key = f"site/hero/{asset_id}.{extension}"
    FilesystemMediaStorage(root).write(storage_key, [payload])
    return MediaAsset.objects.create(
        id=asset_id,
        owner=owner,
        purpose=MediaPurpose.HERO,
        storage_key=storage_key,
        original_name=f"hero.{extension}",
        detected_mime=(DetectedFormat.WEBM if video else DetectedFormat.PNG),
        size_bytes=len(payload),
        sha256=sha256(payload).hexdigest(),
        width=96,
        height=54,
        state=MediaState.ACTIVE,
    )


def _update(
    actor: Account,
    *,
    hero_asset_id: str | None,
    site_name: str | None = None,
) -> None:
    row = SiteConfiguration.objects.get(pk=1)
    update_site_configuration(
        actor_id=actor.id,
        site_name=site_name or row.site_name,
        site_description=row.site_description,
        copyright_text=row.copyright_text,
        registration_enabled=row.registration_enabled,
        article_body_max_bytes=row.article_body_max_bytes,
        logo_asset_id=row.logo_asset_id,
        hero_asset_id=hero_asset_id,
        backup_destination=row.backup_destination,
        expected_version=row.row_version,
        trace_code=f"trc_{'h' * 26}",
        client_ip="127.0.0.1",
    )


def test_hero_configuration_replaces_and_clears_one_public_binding(
    isolated_media_root: Path,
) -> None:
    cache.clear()
    administrator = _account("hero-configuration", administrator=True)
    image = _asset(isolated_media_root, administrator)
    video = _asset(isolated_media_root, administrator, video=True)
    storage = FilesystemMediaStorage(isolated_media_root)

    _update(administrator, hero_asset_id=image.id)
    row = SiteConfiguration.objects.get(pk=1)
    assert row.hero_asset_id == image.id
    assert MediaBinding.objects.filter(
        asset=image,
        target_type=MediaTargetType.SITE_BRAND,
        target_id="site",
        slot="hero",
    ).exists()
    configured = public_site_configuration()
    assert configured.hero_url == f"/_kaj/media/{image.id}"
    assert configured.hero_is_video is False

    _update(administrator, hero_asset_id=video.id)
    image.refresh_from_db()
    assert image.state == MediaState.DELETED
    assert not storage.exists(image.storage_key)
    configured = public_site_configuration()
    assert configured.hero_url == f"/_kaj/media/{video.id}"
    assert configured.hero_is_video is True

    _update(administrator, hero_asset_id=None)
    video.refresh_from_db()
    assert video.state == MediaState.DELETED
    assert not storage.exists(video.storage_key)
    configured = public_site_configuration()
    assert configured.hero_asset_id is None
    assert configured.hero_url is None
    assert configured.hero_is_video is False


def test_hero_replacement_failure_rolls_back_configuration_and_binding(
    isolated_media_root: Path,
) -> None:
    cache.clear()
    administrator = _account("hero-atomic", administrator=True)
    other = _account("hero-other")
    current = _asset(isolated_media_root, administrator)
    wrong_owner = _asset(isolated_media_root, other, video=True)
    _update(administrator, hero_asset_id=current.id)
    before = SiteConfiguration.objects.get(pk=1)

    with pytest.raises(SiteContentCommandError):
        _update(
            administrator,
            hero_asset_id=wrong_owner.id,
            site_name="不应保存的站点名",
        )

    after = SiteConfiguration.objects.get(pk=1)
    assert after.site_name == before.site_name
    assert after.hero_asset_id == current.id
    assert after.row_version == before.row_version
    assert MediaBinding.objects.filter(
        asset=current,
        target_type=MediaTargetType.SITE_BRAND,
        target_id="site",
        slot="hero",
    ).exists()
    assert not wrong_owner.bindings.exists()


def test_home_hero_renders_default_image_custom_image_and_safe_video(
    client,
    isolated_media_root: Path,
) -> None:
    cache.clear()
    administrator = _account("hero-home", administrator=True)
    image = _asset(isolated_media_root, administrator)
    video = _asset(isolated_media_root, administrator, video=True)

    default_response = client.get(reverse("public:home"))
    assert default_response.status_code == 200
    assert 'class="home-hero__image"' in default_response.content.decode()
    assert "data-home-hero-video" not in default_response.content.decode()

    _update(administrator, hero_asset_id=image.id)
    image_html = client.get(reverse("public:home")).content.decode()
    assert f'src="/_kaj/media/{image.id}"' in image_html
    assert "data-home-hero-video" not in image_html

    _update(administrator, hero_asset_id=video.id)
    video_html = client.get(reverse("public:home")).content.decode()
    assert f'src="/_kaj/media/{video.id}"' in video_html
    assert "data-home-hero-video" in video_html
    assert " muted" in video_html
    assert " autoplay" in video_html
    assert " loop" in video_html
    assert " playsinline" in video_html
    assert " disablepictureinpicture" in video_html
    assert " disableremoteplayback" in video_html
    assert "data-home-hero-control" in video_html
    assert "default-cover.png" in video_html


def test_site_hero_picker_accepts_images_and_supported_video() -> None:
    form = SiteConfigurationForm()
    assert form.fields["hero_asset_id"].widget.is_hidden
    html = render_to_string(
        "media/partials/picker.html",
        {
            "adapter": "site-hero",
            "upload_url": "/media/picker-uploads/site-hero/",
            "input_name": "hero_asset_id",
            "label": "首页主视觉",
            "picker_id": "site-hero",
            "current_asset_id": "",
            "current_preview_url": "",
            "current_is_video": False,
        },
    )
    assert 'data-media-kind="hero"' in html
    assert ".mp4" in html
    assert ".webm" in html
    assert "data-media-video-preview" in html
    assert 'aria-label="移除首页主视觉"' in html


def test_public_configuration_uses_default_hero_before_schema_expansion(
    monkeypatch,
) -> None:
    cache.clear()
    monkeypatch.setattr(
        "apps.navigation.queries.site_content.site_hero_column_available",
        lambda: False,
    )

    configured = public_site_configuration()

    assert configured.hero_configuration_available is False
    assert configured.hero_asset_id is None
    assert configured.hero_url is None


def test_other_site_settings_remain_writable_before_hero_schema_expansion(
    monkeypatch,
) -> None:
    administrator = _account("hero-expand", administrator=True)
    monkeypatch.setattr(
        "apps.navigation.services.site_settings.site_hero_column_available",
        lambda: False,
    )
    row = SiteConfiguration.objects.get(pk=1)

    _update(
        administrator,
        hero_asset_id=None,
        site_name="迁移前仍可保存",
    )

    row.refresh_from_db()
    assert row.site_name == "迁移前仍可保存"
    assert row.row_version == 2
