import threading
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Account, LoginSession, NicknameHistory
from apps.accounts.queries.profile import public_account_identity
from apps.accounts.services.profile import (
    ProfileError,
    change_profile,
    validate_nickname,
)
from apps.media.public import MediaPurpose, authorize_asset_read, stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, nickname: str | None = None) -> Account:
    return Account.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
        nickname=nickname,
    )


def _audit(**values):
    return values


def _change(account: Account, **overrides) -> Account:
    values = {
        "account_id": account.id,
        "nickname": account.nickname,
        "theme": account.theme,
        "avatar_asset_id": account.avatar_asset_id,
        "client_ip": "127.0.0.1",
        "trace_code": "KJ-ACC007-TEST",
        "audit_writer": _audit,
    }
    values.update(overrides)
    return change_profile(**values)


@pytest.mark.parametrize(
    ("nickname", "budget"),
    [
        ("A", 1),
        ("中文", 4),
        ("Kaj小房间", 9),
        ("Straße", 6),
        ("中文中文中文中文", 16),
        ("abcdefghijklmnop", 16),
    ],
)
def test_nickname_validation_preserves_display_and_counts_unicode(
    nickname: str, budget: int
) -> None:
    validated = validate_nickname(f"  {nickname}  ")
    assert validated.display == nickname
    assert validated.budget == budget


@pytest.mark.parametrize(
    "nickname",
    [
        "abcdefghijklmnopq",
        "中文中文中文中文A",
        "Kaj_房间",
        "Kaj  房间",
        "Kaj1",
        "Kaj!",
    ],
)
def test_nickname_validation_rejects_over_budget_and_non_letters(
    nickname: str,
) -> None:
    with pytest.raises(ValidationError):
        validate_nickname(nickname)


def test_change_profile_preserves_case_records_history_and_enforces_cooldown() -> None:
    account = _account("profile-history")
    now = timezone.now()
    changed = _change(account, nickname="Kaj房间", now=now)
    assert changed.nickname == "Kaj房间"
    assert changed.normalized_nickname == "kaj房间"
    assert changed.nickname_changed_at == now
    history = NicknameHistory.objects.get(account=account)
    assert history.previous_nickname is None
    assert history.nickname == "Kaj房间"
    assert history.changed_at == now

    with pytest.raises(ProfileError) as caught:
        _change(changed, nickname="新名字", now=now + timedelta(days=6, hours=23))
    assert caught.value.field == "nickname"
    changed.refresh_from_db()
    assert changed.nickname == "Kaj房间"

    theme_only = _change(changed, theme=Account.Theme.DARK, now=now + timedelta(days=1))
    assert theme_only.theme == Account.Theme.DARK
    renamed = _change(theme_only, nickname="KAJ房间", now=now + timedelta(days=7))
    assert renamed.nickname == "KAJ房间"
    assert NicknameHistory.objects.filter(account=account).count() == 2


def test_nickname_cooldown_message_uses_shanghai_time() -> None:
    account = _account("profile-cooldown-timezone")
    changed_at = datetime(2026, 7, 23, 18, 30, tzinfo=UTC)
    changed = _change(account, nickname="上海时间", now=changed_at)

    with pytest.raises(ProfileError) as caught:
        _change(changed, nickname="冷却中", now=changed_at + timedelta(days=1))

    assert caught.value.field == "nickname"
    assert "2026-07-31 02:30" in str(caught.value)


def test_casefold_conflict_has_one_service_winner_under_concurrency() -> None:
    accounts = (_account("profile-race-one"), _account("profile-race-two"))
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker(account_id, nickname: str) -> None:
        close_old_connections()
        try:
            account = Account.objects.get(pk=account_id)
            barrier.wait(timeout=5)
            _change(account, nickname=nickname)
        except ProfileError:
            outcomes.append("conflict")
        else:
            outcomes.append("changed")
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=worker, args=(accounts[0].id, "CaseFold")),
        threading.Thread(target=worker, args=(accounts[1].id, "CASEFOLD")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ["changed", "conflict"]
    assert Account.objects.filter(normalized_nickname="casefold").count() == 1


def _avatar(owner: Account, root: Path):
    image = BytesIO()
    Image.new("RGB", (32, 32), "#7e2637").save(image, format="PNG")
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.AVATAR,
        original_name="profile.png",
        declared_content_type="image/png",
        chunks=[image.getvalue()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
    )


def test_avatar_change_uses_media_binding_and_rejects_another_owner(
    isolated_media_root: Path,
) -> None:
    owner = _account("profile-avatar")
    stranger = _account("profile-avatar-other")
    asset = _avatar(owner, isolated_media_root)

    changed = _change(owner, avatar_asset_id=asset.id)
    assert changed.avatar_asset_id == asset.id
    authorization = authorize_asset_read(asset_id=asset.id, actor_id=None)
    assert authorization.asset_id == asset.id
    assert authorization.public_immutable is True
    identity = public_account_identity(owner.id)
    assert identity.avatar_url == f"/_kaj/media/{asset.id}"
    assert "email" not in identity.__dataclass_fields__

    with pytest.raises(ProfileError) as caught:
        _change(stranger, avatar_asset_id=asset.id)
    assert caught.value.field == "avatar_asset_id"
    stranger.refresh_from_db()
    assert stranger.avatar_asset_id is None

    removed = _change(changed, avatar_asset_id=None)
    assert removed.avatar_asset_id is None
    asset.refresh_from_db()
    assert asset.state == "DELETED"
    assert not FilesystemMediaStorage(isolated_media_root).exists(asset.storage_key)


def test_profile_audit_failure_rolls_back_account_and_avatar_binding(
    isolated_media_root: Path,
) -> None:
    account = _account("profile-audit-rollback")
    asset = _avatar(account, isolated_media_root)

    def reject_audit(**values):
        del values
        raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        _change(
            account,
            nickname="Rollback",
            avatar_asset_id=asset.id,
            audit_writer=reject_audit,
        )
    account.refresh_from_db()
    asset.refresh_from_db()
    assert account.nickname is None
    assert account.avatar_asset_id is None
    assert asset.state == "ACTIVE"
    assert not asset.bindings.exists()
    assert NicknameHistory.objects.filter(account=account).count() == 0
    assert FilesystemMediaStorage(isolated_media_root).exists(asset.storage_key)


def test_public_identity_falls_back_without_email_and_deleted_identity_is_reusable() -> (
    None
):
    old = Account.objects.create_account(
        email="fallback.person@kaj.test",
        password="Valid-password-1",
        nickname="Reusable",
    )
    old_id = old.id
    identity = public_account_identity(old.id)
    assert identity.display_name == "Reusable"
    assert identity.avatar_initial == "R"
    assert "fallback.person@kaj.test" not in repr(identity)

    old.delete()
    replacement = Account.objects.create_account(
        email="replacement@kaj.test",
        password="Valid-password-1",
        nickname="REUSABLE",
    )
    assert replacement.id != old_id
    assert not NicknameHistory.objects.filter(account_id=old_id).exists()

    fallback = _account("fallback-display")
    fallback_identity = public_account_identity(fallback.id)
    assert fallback.email not in repr(fallback_identity)
    assert fallback_identity.display_name == fallback.email.partition("@")[0]
    assert fallback_identity.avatar_initial == fallback.email[0]


def test_settings_profile_theme_and_empty_public_page_flow() -> None:
    account = _account("profile-http")
    conflict = _account("profile-conflict", nickname="TakenName")
    raw_token, _ = LoginSession.issue(account=account, remember=False)
    client = Client()
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token

    page = client.get("/accounts/settings/?tab=profile")
    body = page.content.decode()
    assert page.status_code == 200
    assert 'role="tablist"' in body
    assert 'data-media-picker="avatar"' in body
    picker = body.split('data-media-picker="avatar"', 1)[1]
    assert 'name="csrfmiddlewaretoken"' in picker

    invalid = client.post(
        "/accounts/settings/",
        {"action": "change_profile", "nickname": "Bad!", "avatar_asset_id": ""},
    )
    assert invalid.status_code == 422
    assert "昵称只能使用文字" in invalid.content.decode()
    duplicate = client.post(
        "/accounts/settings/",
        {
            "action": "change_profile",
            "nickname": conflict.nickname.swapcase(),
            "avatar_asset_id": "",
        },
    )
    assert duplicate.status_code == 422
    assert "昵称已被使用" in duplicate.content.decode()

    themed = client.post(
        "/accounts/settings/",
        {"action": "change_theme", "theme": "dark"},
    )
    assert themed.status_code == 302
    account.refresh_from_db()
    assert account.theme == Account.Theme.DARK
    cross_device = client.get("/accounts/settings/?tab=theme")
    assert 'data-theme="dark"' in cross_device.content.decode()
    assert 'data-theme-source="account"' in cross_device.content.decode()

    public = Client().get(f"/people/{account.id}/")
    public_body = public.content.decode()
    assert public.status_code == 200
    assert "此处还没有公开文章" in public_body
    assert account.email not in public_body
    assert 'class="profile-avatar profile-avatar--generated"' in public_body
