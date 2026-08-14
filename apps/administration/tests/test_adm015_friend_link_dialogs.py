import json
from uuid import uuid4

import pytest
from django.conf import settings
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.navigation.models import FriendLink, SiteConfiguration

pytestmark = pytest.mark.django_db(transaction=True)


def _administrator_client(client):
    administrator = Account.objects.create_account(
        email=f"friend-dialog-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(account=administrator, role="AUTHOR")
    RoleAssignment.objects.create(account=administrator, role="ADMINISTRATOR")
    token, _session = LoginSession.issue(
        account=administrator,
        remember=False,
        client_ip="127.0.0.1",
    )
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    SiteConfiguration.objects.get_or_create(pk=1)
    return administrator


def _friend_link(*, name="示例站点", position=0):
    return FriendLink.objects.create(
        name=name,
        url="https://example.com",
        description="用于验证友情链接弹窗。",
        logo_asset_id="",
        position=position,
    )


def test_friend_links_render_as_compact_list_without_inline_forms(client) -> None:
    _administrator_client(client)
    link = _friend_link()

    response = client.get(reverse("admin:site-settings"))
    body = response.content.decode()

    assert response.status_code == 200
    assert 'id="friend-link-manager"' in body
    assert 'id="friend-link-create"' in body
    assert f'id="friend-link-edit-{link.id}"' in body
    assert f'id="friend-link-delete-{link.id}"' in body
    assert 'id="friend-link-dialog-host"' in body
    assert "friend-link-editor" not in body
    assert f'name="friend-{link.id}-name"' not in body
    assert 'name="friend-new-name"' not in body


def test_friend_link_create_and_edit_share_the_dialog_form(client) -> None:
    _administrator_client(client)
    link = _friend_link()
    url = reverse("admin:site-settings")

    create = client.get(
        url,
        {"friend_dialog": "create"},
        HTTP_HX_REQUEST="true",
    )
    create_body = create.content.decode()
    assert create.status_code == 200
    assert 'id="friend-link-dialog"' in create_body
    assert "新增友情链接" in create_body
    assert 'name="friend-new-name"' in create_body
    assert 'hx-target="#friend-link-manager"' in create_body

    edit = client.get(
        url,
        {"friend_dialog": "edit", "link_id": str(link.id)},
        HTTP_HX_REQUEST="true",
    )
    edit_body = edit.content.decode()
    assert edit.status_code == 200
    assert 'id="friend-link-dialog"' in edit_body
    assert "编辑友情链接" in edit_body
    assert f'name="friend-{link.id}-name"' in edit_body
    assert 'value="示例站点"' in edit_body

    fallback = client.get(
        url,
        {"friend_dialog": "edit", "link_id": str(link.id)},
    )
    fallback_body = fallback.content.decode()
    assert fallback.status_code == 200
    assert "data-auto-modal" in fallback_body
    assert f'data-dialog-return-focus="friend-link-edit-{link.id}"' in fallback_body


def test_friend_link_dialog_keeps_422_and_refreshes_success_in_place(client) -> None:
    _administrator_client(client)
    url = reverse("admin:site-settings")

    invalid = client.post(
        url,
        {
            "action": "friend_create",
            "friend-new-name": "保留输入的站点",
            "friend-new-url": "http://example.com",
            "friend-new-description": "描述",
            "friend-new-position": "0",
        },
        HTTP_HX_REQUEST="true",
    )
    invalid_body = invalid.content.decode()
    assert invalid.status_code == 422
    assert invalid.headers["HX-Retarget"] == "#friend-link-dialog-host"
    assert invalid.headers["HX-Reswap"] == "innerHTML"
    assert "保留输入的站点" in invalid_body
    assert "外链必须使用不含凭据的 HTTPS 地址" in invalid_body
    assert "data-error-focus" in invalid_body

    created = client.post(
        url,
        {
            "action": "friend_create",
            "friend-new-name": "新增站点",
            "friend-new-url": "https://example.org/path",
            "friend-new-description": "成功后只刷新列表。",
            "friend-new-position": "0",
        },
        HTTP_HX_REQUEST="true",
    )
    created_body = created.content.decode()
    assert created.status_code == 200
    assert 'id="friend-link-manager"' in created_body
    assert "新增站点" in created_body
    assert 'id="friend-link-dialog"' not in created_body
    trigger = json.loads(created.headers["HX-Trigger-After-Swap"])
    assert trigger["kaj:feedback"]["message"] == "友情链接已新增。"
    created_link = FriendLink.objects.get()
    assert trigger["kaj:focus"]["id"] == f"friend-link-edit-{created_link.id}"
    assert created_link.url == "https://example.org/path"


def test_friend_link_edit_and_delete_use_versioned_dialog_actions(client) -> None:
    _administrator_client(client)
    link = _friend_link()
    url = reverse("admin:site-settings")

    updated = client.post(
        url,
        {
            "action": "friend_update",
            "link_id": str(link.id),
            f"friend-{link.id}-link_id": str(link.id),
            f"friend-{link.id}-name": "更新后的站点",
            f"friend-{link.id}-url": "https://example.net",
            f"friend-{link.id}-description": "更新后的描述。",
            f"friend-{link.id}-position": "0",
            f"friend-{link.id}-expected_version": str(link.row_version),
        },
        HTTP_HX_REQUEST="true",
    )
    assert updated.status_code == 200
    assert "更新后的站点" in updated.content.decode()
    link.refresh_from_db()

    confirm = client.get(
        url,
        {"friend_dialog": "delete", "link_id": str(link.id)},
        HTTP_HX_REQUEST="true",
    )
    confirm_body = confirm.content.decode()
    assert confirm.status_code == 200
    assert "删除这个友情链接？" in confirm_body
    assert f'name="delete-{link.id}-expected_version"' in confirm_body

    deleted = client.post(
        url,
        {
            "action": "friend_delete",
            "link_id": str(link.id),
            f"delete-{link.id}-link_id": str(link.id),
            f"delete-{link.id}-expected_version": str(link.row_version),
        },
        HTTP_HX_REQUEST="true",
    )
    assert deleted.status_code == 200
    assert "还没有友情链接" in deleted.content.decode()
    assert not FriendLink.objects.exists()
