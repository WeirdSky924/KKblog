from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.administration.forms.site_settings import FriendLinkForm
from apps.media.upload_adapters import default_media_upload_adapters
from apps.navigation.models import FriendLink
from apps.navigation.public import (
    SiteContentCommandError,
    create_friend_link,
    delete_friend_link,
    update_friend_link,
    visible_friend_links,
)
from apps.operations.models import AuditEntry
from config.navigation_integrations import configure_navigation_integrations

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _configure_integrations() -> None:
    configure_navigation_integrations()


def _administrator():
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"friend-link-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token


def _meta() -> dict[str, str]:
    return {"trace_code": f"trc_{'f' * 26}", "client_ip": "127.0.0.1"}


def test_friend_link_domain_creates_updates_and_deletes_without_logo() -> None:
    administrator = _administrator()

    first = create_friend_link(
        actor_id=administrator.id,
        name="示例站点",
        url="https://example.com/path",
        description="用于验证无 Logo 的友情链接。",
        position=0,
        **_meta(),
    )
    second = create_friend_link(
        actor_id=administrator.id,
        name="第二站点",
        url="https://example.org",
        description="第二条友情链接。",
        position=1,
        **_meta(),
    )

    changed = update_friend_link(
        actor_id=administrator.id,
        link_id=second.link_id,
        name="第二站点（更新）",
        url="https://example.org/updated",
        description="修改后仍不需要 Logo。",
        position=0,
        expected_version=second.row_version,
        **_meta(),
    )
    items = visible_friend_links()
    assert [item.name for item in items] == ["第二站点(更新)", "示例站点"]
    assert not hasattr(items[0], "logo_asset_id")
    assert not hasattr(items[0], "logo_url")
    with pytest.raises(SiteContentCommandError) as invalid_url:
        create_friend_link(
            actor_id=administrator.id,
            name="不安全站点",
            url="http://example.net/?source=unsafe",
            description="不能写入。",
            position=2,
            **_meta(),
        )
    assert getattr(invalid_url.value, "code", "") == (
        "navigation.friend_link_url_invalid.v1"
    )

    delete_friend_link(
        actor_id=administrator.id,
        link_id=changed.link_id,
        expected_version=changed.row_version,
        **_meta(),
    )
    assert list(FriendLink.objects.values_list("name", "position")) == [("示例站点", 0)]
    assert first.link_id == FriendLink.objects.get().id
    audits = AuditEntry.objects.filter(target_type="friend_link").order_by(
        "created_at", "id"
    )
    assert set(audits.values_list("action", flat=True)) == {
        "navigation.friend_link.create",
        "navigation.friend_link.update",
        "navigation.friend_link.reorder",
        "navigation.friend_link.delete",
    }
    assert all(
        "logo_asset_id" not in snapshot
        for entry in audits
        for snapshot in (entry.before_safe, entry.after_safe)
    )
    assert audits.filter(
        action="navigation.friend_link.delete",
        target_id=str(changed.link_id),
    ).exists()


def test_friend_link_form_and_public_page_have_no_logo_contract(client) -> None:
    administrator = _administrator()
    created = create_friend_link(
        actor_id=administrator.id,
        name="公开站点",
        url="https://example.com",
        description="公开页面只展示名称和描述。",
        position=0,
        **_meta(),
    )

    assert "logo_asset_id" not in FriendLinkForm().fields
    legacy_field = FriendLink._meta.get_field("logo_asset_id")
    assert legacy_field.blank is True
    assert legacy_field.get_default() == ""

    response = client.get(reverse("public:friend-links"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "公开站点" in body
    assert "公开页面只展示名称和描述。" in body
    assert 'href="https://example.com"' in body
    friend_link_markup = body.split('<li class="public-friend-link">', 1)[1].split(
        "</li>", 1
    )[0]
    assert "<img" not in friend_link_markup
    assert str(created.link_id) not in body


def test_retired_friend_logo_upload_adapter_is_not_resolvable(client) -> None:
    administrator = _administrator()
    _authenticate(client, administrator)

    with pytest.raises(ValidationError):
        default_media_upload_adapters.resolve("friend-logo")
    response = client.post(
        reverse("media:upload", kwargs={"adapter": "friend-logo"}),
        {},
    )
    assert response.status_code == 404
