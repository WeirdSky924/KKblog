import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.core.events.models import OutboxEvent

pytestmark = pytest.mark.django_db(transaction=True)


def _client_for(account: Account) -> Client:
    token, _session = LoginSession.issue(account=account, remember=False)
    client = Client(REMOTE_ADDR="127.0.0.1")
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def test_non_author_can_request_author_permission_once():
    account = Account.objects.create_account(
        email="author-request@kaj.test",
        password="Valid-password-1",
        nickname="申请者",
    )
    client = _client_for(account)
    entry_url = reverse("authoring:articles")

    home = client.get(reverse("public:home"))
    assert home.status_code == 200
    assert 'aria-label="进入我的文章"' in home.content.decode()

    first_page = client.get(entry_url)
    assert first_page.status_code == 200
    assert "你还没有作者权限" in first_page.content.decode()
    assert "申请作者权限" in first_page.content.decode()
    assert client.get(reverse("authoring:create")).status_code == 403

    first_submit = client.post(
        entry_url,
        {"action": "request_author_permission"},
    )
    assert first_submit.status_code == 302

    account.refresh_from_db()
    assert account.author_permission_requested_at is not None
    assert (
        OutboxEvent.objects.filter(
            event_type="account.author_permission_requested.v1",
            aggregate_id=str(account.id),
        ).count()
        == 1
    )

    submitted_page = client.get(entry_url)
    submitted_body = submitted_page.content.decode()
    assert "已通知管理员申请作者权限" in submitted_body
    assert 'name="action" value="request_author_permission"' not in submitted_body

    repeated_submit = client.post(
        entry_url,
        {"action": "request_author_permission"},
    )
    assert repeated_submit.status_code == 302
    assert (
        OutboxEvent.objects.filter(
            event_type="account.author_permission_requested.v1",
            aggregate_id=str(account.id),
        ).count()
        == 1
    )


def test_author_keeps_the_existing_article_workspace():
    account = Account.objects.create_account(
        email="existing-author@kaj.test",
        password="Valid-password-1",
        nickname="作者",
    )
    RoleAssignment.objects.create(account=account, role=RoleAssignment.Role.AUTHOR)

    response = _client_for(account).get(reverse("authoring:articles"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "新建文章" in body
    assert "你还没有作者权限" not in body
