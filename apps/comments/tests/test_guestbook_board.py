from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.comments.models import Comment
from apps.comments.queries import guestbook_board_page
from apps.comments.services import sync_guestbook_thread
from apps.core.ids import new_ulid

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, roles: tuple[str, ...] = ()):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _client(account, address: str) -> Client:
    token, _ = apps.get_model("accounts", "LoginSession").issue(
        account=account,
        remember=False,
    )
    client = Client(REMOTE_ADDR=address)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def _comment(thread, author, body: str, *, minutes_ago: int = 0, hidden=False, flag=""):
    created_at = timezone.now() - timedelta(minutes=minutes_ago)
    identity = new_ulid()
    return Comment.objects.create(
        id=identity,
        thread=thread,
        parent=None,
        root_id=identity,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=body,
        state=Comment.State.VISIBLE,
        visible_at=created_at,
        guestbook_hidden=hidden,
        guestbook_flag=flag,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.140",
        created_at=created_at,
    )


def test_home_guestbook_requires_member_and_publishes_plain_text() -> None:
    administrator = _account("guestbook-board-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("guestbook-board-member")
    sync_guestbook_thread()
    post_url = reverse("public:guestbook-board-comment-create")
    visitor = Client(REMOTE_ADDR="198.51.100.140")
    member_client = _client(member, "198.51.100.141")

    home = visitor.get(reverse("public:home"))
    home_html = home.content.decode()
    assert home.status_code == 200
    assert "data-home-guestbook-shell" in home_html
    assert "登录后留言" in home_html
    member_home = member_client.get(reverse("public:home"))
    member_home_html = member_home.content.decode()
    assert f'action="{post_url}"' in member_home_html
    assert "home-guestbook-dialog__header" in member_home_html
    assert "home-guestbook-dialog__form" in member_home_html
    assert 'data-lucide="x"' in member_home_html

    denied = visitor.post(
        post_url,
        {"surface": "home", "body": "匿名不能发布"},
        HTTP_HX_REQUEST="true",
    )
    assert denied.status_code == 403
    assert not Comment.objects.filter(body="匿名不能发布").exists()

    created = member_client.post(
        post_url,
        {"body": "首页即时留言"},
        HTTP_HX_REQUEST="true",
    )
    assert created.status_code == 201
    comment = Comment.objects.get(body="首页即时留言")
    assert comment.author_id == member.id
    assert comment.state == Comment.State.VISIBLE
    assert comment.visible_at == comment.created_at

    invalid_cjk = member_client.post(
        post_url,
        {"body": "中" * 51},
        HTTP_HX_REQUEST="true",
    )
    invalid_newline = member_client.post(
        post_url,
        {"body": "不允许\n换行"},
        HTTP_HX_REQUEST="true",
    )
    assert invalid_cjk.status_code == 422
    assert invalid_newline.status_code == 422
    assert Comment.objects.filter(thread__target_id="site").count() == 1
    assert administrator.id != member.id


def test_home_guestbook_enforces_account_and_board_daily_limits() -> None:
    administrator = _account("guestbook-limit-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    member = _account("guestbook-limit-member")
    thread = sync_guestbook_thread()
    member_client = _client(member, "198.51.100.142")
    post_url = reverse("public:guestbook-board-comment-create")

    for index in range(2):
        response = member_client.post(
            post_url,
            {"surface": "home", "body": f"用户配额 {index}"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 201
    account_limited = member_client.post(
        post_url,
        {"surface": "home", "body": "用户第三条"},
        HTTP_HX_REQUEST="true",
    )
    assert account_limited.status_code == 429

    for index in range(18):
        _comment(thread, administrator, f"占满留言 {index}", minutes_ago=index + 1)
    board_limited = _client(_account("guestbook-limit-other"), "198.51.100.143").post(
        post_url,
        {"surface": "home", "body": "第 21 条"},
        HTTP_HX_REQUEST="true",
    )
    assert board_limited.status_code == 429
    assert Comment.objects.filter(thread=thread, parent__isnull=True).count() == 20


def test_guestbook_board_is_newest_first_keyset_and_hides_moderated_rows() -> None:
    administrator = _account("guestbook-query-admin", roles=("AUTHOR", "ADMINISTRATOR"))
    thread = sync_guestbook_thread()
    rows = tuple(
        _comment(
            thread,
            administrator,
            f"留言 {index:02d}",
            minutes_ago=index + 1,
            hidden=index == 4,
            flag="READ" if index == 0 else "",
        )
        for index in range(12)
    )

    first = guestbook_board_page(thread_id=thread.id)
    second = guestbook_board_page(thread_id=thread.id, cursor=first.next_cursor)

    assert len(first.items) == 10
    assert first.items[0].body == rows[0].body
    assert all(item.body != rows[4].body for item in first.items + second.items)
    assert first.items[0].flag == "READ"
    assert len(second.items) == 1
    assert second.items[0].body == rows[11].body
    assert second.next_cursor is None


def test_guestbook_admin_can_hide_mark_and_delete() -> None:
    administrator = _account(
        "guestbook-admin-actions", roles=("AUTHOR", "ADMINISTRATOR")
    )
    thread = sync_guestbook_thread()
    hidden_comment = _comment(thread, administrator, "待隐藏留言")
    deleted_comment = _comment(thread, administrator, "待删除留言", minutes_ago=1)
    client = _client(administrator, "198.51.100.144")
    admin_url = reverse("admin:guestbook")

    page = client.get(admin_url)
    assert page.status_code == 200
    assert "待隐藏留言" in page.content.decode()

    hidden = client.post(
        admin_url,
        {
            "action": "guestbook_moderate",
            "comment_id": hidden_comment.id,
            "operation": "HIDE",
            "flag": "",
        },
    )
    assert hidden.status_code == 302
    hidden_comment.refresh_from_db()
    assert hidden_comment.guestbook_hidden is True

    marked = client.post(
        admin_url,
        {
            "action": "guestbook_moderate",
            "comment_id": hidden_comment.id,
            "operation": "MARK",
            "flag": "DONE",
        },
    )
    assert marked.status_code == 302
    hidden_comment.refresh_from_db()
    assert hidden_comment.guestbook_flag == "DONE"

    deleted = client.post(
        admin_url,
        {
            "action": "guestbook_delete",
            "comment_id": deleted_comment.id,
            "reason": "测试删除",
            "confirm": "comment_delete",
        },
    )
    assert deleted.status_code == 302
    deleted_comment.refresh_from_db()
    assert deleted_comment.state == Comment.State.DELETED
