from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.content.models import Section
from apps.content.public import (
    SectionCommandError,
    admin_section_item,
    create_section,
    delete_section,
    update_section,
)
from apps.core.observability.trace import new_trace_code
from apps.media.models import (
    MediaAsset,
    MediaBinding,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    authorize_asset_read,
    replace_bindings,
    stage_upload,
)
from apps.media.storage.filesystem import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (48, 32), "#7e2637").save(stream, format="PNG")
    return stream.getvalue()


def _cover(owner, media_root: Path) -> MediaAsset:
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.SECTION_COVER,
        original_name="section.png",
        declared_content_type="image/png",
        chunks=(_png(),),
        storage=FilesystemMediaStorage(media_root),
        capacity_check=lambda: None,
    )


def test_section_cover_upload_is_administrator_only(
    client, isolated_media_root: Path
) -> None:
    member = _account("section-cover-member")
    _authenticate(client, member)
    denied = client.post(
        reverse("media:upload", kwargs={"adapter": "section-cover"}),
        {"file": SimpleUploadedFile("cover.png", _png(), "image/png")},
    )
    assert denied.status_code == 404

    administrator = _account("section-cover-admin", administrator=True)
    _authenticate(client, administrator)
    accepted = client.post(
        reverse("media:upload", kwargs={"adapter": "section-cover"}),
        {"file": SimpleUploadedFile("cover.png", _png(), "image/png")},
    )
    assert accepted.status_code == 201
    asset = MediaAsset.objects.get(owner=administrator)
    assert asset.purpose == MediaPurpose.SECTION_COVER
    assert (isolated_media_root / asset.storage_key).is_file()


def test_create_section_persists_and_binds_one_default_cover(
    isolated_media_root: Path,
) -> None:
    administrator = _account("section-create-cover", administrator=True)
    cover = _cover(administrator, isolated_media_root)

    result = create_section(
        actor_id=administrator.id,
        name="默认封面分区",
        default_cover_asset_id=cover.id,
        **_context(),
    )

    section = Section.objects.get(pk=result.section_id)
    assert result.default_cover_asset_id == cover.id
    assert (
        admin_section_item(
            actor_id=administrator.id, section_id=section.id
        ).default_cover_asset_id
        == cover.id
    )
    binding = MediaBinding.objects.get(
        target_type=MediaTargetType.SECTION,
        target_id=str(section.id),
    )
    assert (binding.asset_id, binding.slot) == (cover.id, "default-cover")
    assert (
        authorize_asset_read(
            actor_id=None,
            asset_id=cover.id,
        ).public_immutable
        is True
    )


def test_section_cover_rejects_wrong_owner_and_purpose_without_partial_binding(
    isolated_media_root: Path,
) -> None:
    administrator = _account("section-cover-owner", administrator=True)
    other = _account("section-cover-other")
    wrong_owner = _cover(other, isolated_media_root)

    with pytest.raises(SectionCommandError) as captured:
        create_section(
            actor_id=administrator.id,
            name="不应创建",
            default_cover_asset_id=wrong_owner.id,
            **_context(),
        )
    assert captured.value.code == "media.asset_owner_mismatch.v1"
    assert not Section.objects.filter(name="不应创建").exists()
    assert not wrong_owner.bindings.exists()

    plain_cover = stage_upload(
        owner_id=administrator.id,
        purpose=MediaPurpose.COVER,
        original_name="article.png",
        declared_content_type="image/png",
        chunks=(_png(),),
        storage=FilesystemMediaStorage(isolated_media_root),
        capacity_check=lambda: None,
        target_id="01HZX3N4YZ6B8Q1M2D5K7R9TVC",
    )
    section = create_section(
        actor_id=administrator.id,
        name="保留空封面",
        **_context(),
    )
    with pytest.raises(SectionCommandError) as captured:
        update_section(
            actor_id=administrator.id,
            section_id=section.section_id,
            name=section.name,
            default_cover_asset_id=plain_cover.id,
            **_context(),
        )
    assert captured.value.code == "media.binding_purpose_mismatch.v1"
    assert (
        admin_section_item(
            actor_id=administrator.id,
            section_id=section.section_id,
        ).default_cover_asset_id
        is None
    )
    assert not plain_cover.bindings.exists()


def test_update_section_replaces_and_clears_cover_through_media_lifecycle(
    isolated_media_root: Path,
) -> None:
    administrator = _account("section-replace-cover", administrator=True)
    first = _cover(administrator, isolated_media_root)
    second = _cover(administrator, isolated_media_root)
    section = create_section(
        actor_id=administrator.id,
        name="可换封面",
        default_cover_asset_id=first.id,
        **_context(),
    )

    updated = update_section(
        actor_id=administrator.id,
        section_id=section.section_id,
        name="已换封面",
        default_cover_asset_id=second.id,
        **_context(),
    )
    assert updated.default_cover_asset_id == second.id
    first.refresh_from_db()
    assert first.state == MediaState.DELETED
    assert not (isolated_media_root / first.storage_key).exists()

    cleared = update_section(
        actor_id=administrator.id,
        section_id=section.section_id,
        name="已换封面",
        default_cover_asset_id=None,
        **_context(),
    )
    assert cleared.default_cover_asset_id is None
    second.refresh_from_db()
    assert second.state == MediaState.DELETED
    assert not MediaBinding.objects.filter(
        target_type=MediaTargetType.SECTION,
        target_id=str(section.section_id),
    ).exists()


def test_failed_update_rolls_back_binding_and_delete_releases_file(
    isolated_media_root: Path,
) -> None:
    administrator = _account("section-cover-rollback", administrator=True)
    retained = _cover(administrator, isolated_media_root)
    replacement = _cover(administrator, isolated_media_root)
    first = create_section(
        actor_id=administrator.id,
        name="不能重名甲",
        default_cover_asset_id=retained.id,
        **_context(),
    )
    create_section(
        actor_id=administrator.id,
        name="不能重名乙",
        **_context(),
    )

    with pytest.raises(SectionCommandError) as captured:
        update_section(
            actor_id=administrator.id,
            section_id=first.section_id,
            name="不能重名乙",
            default_cover_asset_id=replacement.id,
            **_context(),
        )
    assert captured.value.code == "content.section_name_conflict.v1"
    current = admin_section_item(
        actor_id=administrator.id,
        section_id=first.section_id,
    )
    assert current.default_cover_asset_id == retained.id
    assert retained.bindings.filter(target_id=str(first.section_id)).exists()
    assert not replacement.bindings.exists()

    delete_section(
        actor_id=administrator.id,
        section_id=first.section_id,
        **_context(),
    )
    retained.refresh_from_db()
    assert retained.state == MediaState.DELETED
    assert not (isolated_media_root / retained.storage_key).exists()
    assert not MediaBinding.objects.filter(
        target_type=MediaTargetType.SECTION,
        target_id=str(first.section_id),
    ).exists()


def test_media_rule_allows_only_one_section_cover() -> None:
    administrator = _account("section-cover-limit", administrator=True)
    section = create_section(
        actor_id=administrator.id,
        name="单张封面",
        **_context(),
    )
    assets = [
        MediaAsset.objects.create(
            owner=administrator,
            purpose=MediaPurpose.SECTION_COVER,
            storage_key=f"site/sections/{index}.png",
            original_name="section.png",
            detected_mime="image/png",
            size_bytes=1,
            sha256=str(index) * 64,
            width=1,
            height=1,
            state=MediaState.ACTIVE,
        )
        for index in (1, 2)
    ]
    with pytest.raises(MediaBindingError) as captured:
        replace_bindings(
            actor_id=administrator.id,
            target_type=MediaTargetType.SECTION,
            target_id=str(section.section_id),
            inputs=tuple(
                BindingInput(asset.id, f"default-cover-{index}")
                for index, asset in enumerate(assets)
            ),
        )
    assert captured.value.code == "media.binding_limit_exceeded.v1"


def test_administration_page_renders_section_cover_create_and_edit_flows(
    client, isolated_media_root: Path
) -> None:
    administrator = _account("section-cover-page", administrator=True)
    cover = _cover(administrator, isolated_media_root)
    section = create_section(
        actor_id=administrator.id,
        name="页面封面分区",
        default_cover_asset_id=cover.id,
        **_context(),
    )
    _authenticate(client, administrator)

    page = client.get(reverse("admin:sections"))
    assert page.status_code == 200
    html = page.content.decode("utf-8")
    assert 'data-media-picker="section-cover"' in html
    assert f"/_kaj/media/{cover.id}" in html
    assert f"?confirm_action=edit&amp;section_id={section.section_id}" in html

    edit = client.get(
        reverse("admin:sections"),
        {"confirm_action": "edit", "section_id": str(section.section_id)},
    )
    assert edit.status_code == 200
    edit_html = edit.content.decode("utf-8")
    assert "编辑文章分区" in edit_html
    assert f'value="{cover.id}"' in edit_html
    assert 'name="action" value="section_update"' in edit_html
