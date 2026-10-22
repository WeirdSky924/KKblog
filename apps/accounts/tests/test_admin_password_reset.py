import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.urls import resolve, reverse
from django.utils import timezone

from apps.accounts.models import (
    Account,
    AdminPasswordReset,
    LoginSession,
    SecurityEvent,
)
from apps.accounts.public import issue_admin_password_reset_link
from apps.operations.public import audit_detail, record_audit_entry, search_audit
from tests.fixtures.accounts import bootstrap_test_administrator

pytestmark = pytest.mark.django_db(transaction=True)


def _client_for(account: Account) -> Client:
    raw_token, _session = LoginSession.issue(
        account=account, remember=False, client_ip="127.0.0.1"
    )
    client = Client(REMOTE_ADDR="127.0.0.1")
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token
    return client


def _password_reset_tokens(mailpit) -> list[str]:
    messages = mailpit.messages()
    tokens = []
    for item in messages:
        message_id = item.get("ID") or item.get("id")
        assert message_id
        message = mailpit.request(f"/api/v1/message/{message_id}")
        assert isinstance(message, dict)
        content = f"{message.get('Text', '')}\n{message.get('HTML', '')}"
        match = re.search(
            r"/accounts/password-reset/link/#([0-9a-f-]{36}\.[A-Za-z0-9_-]{32,128})",
            content,
        )
        assert match is not None
        tokens.append(match.group(1))
    return tokens


def _password_reset_token(mailpit) -> str:
    tokens = _password_reset_tokens(mailpit)
    assert len(tokens) == 1
    return tokens[0]


def _request_reset(admin_client: Client, target: Account) -> None:
    response = admin_client.post(
        reverse("admin:users"),
        {
            "action": "send_password_reset",
            "account_id": str(target.pk),
            "confirm": "password_reset",
        },
    )
    assert response.status_code == 302


def test_admin_password_reset_link_route_is_registered() -> None:
    match = resolve("/accounts/password-reset/link/")

    assert match.view_name == "accounts:admin-password-reset"


def test_admin_can_email_one_time_link_and_reset_revokes_all_sessions(mailpit) -> None:
    admin = bootstrap_test_administrator()
    target = Account.objects.create_account(
        email="reset-link-target@kaj.test", password="Initial-password-1!"
    )
    admin_client = _client_for(admin)
    first_session = LoginSession.issue(account=target, remember=False)[1]
    second_session = LoginSession.issue(account=target, remember=True)[1]

    confirmation = admin_client.get(
        reverse("admin:users"),
        {"confirm_action": "password_reset", "account_id": str(target.pk)},
    )
    assert confirmation.status_code == 200
    assert "30 分钟" in confirmation.content.decode()
    _request_reset(admin_client, target)

    reset_link = _password_reset_token(mailpit)
    reset = AdminPasswordReset.objects.get(account=target)
    first_session.refresh_from_db()
    second_session.refresh_from_db()
    assert first_session.revoked_at is None
    assert second_session.revoked_at is None
    assert reset.token_digest != reset_link
    assert len(reset.token_digest) == 64
    assert reset.expires_at - reset.created_at == timedelta(minutes=30)

    visitor = Client(REMOTE_ADDR="127.0.0.1")
    page = visitor.get(reverse("accounts:admin-password-reset"))
    assert page.status_code == 200
    assert page.headers["Cache-Control"] == "private, no-store"
    assert page.headers["Referrer-Policy"] == "same-origin"
    assert page.context["disable_analytics"] is True

    mismatch = visitor.post(
        reverse("accounts:admin-password-reset"),
        {
            "token": reset_link,
            "new_password": "Changed-password-2!",
            "confirm_password": "Different-password-2!",
        },
    )
    assert mismatch.status_code == 422
    reset.refresh_from_db()
    assert reset.consumed_at is None

    completed = visitor.post(
        reverse("accounts:admin-password-reset"),
        {
            "token": reset_link,
            "new_password": "Changed-password-2!",
            "confirm_password": "Changed-password-2!",
        },
    )
    assert completed.status_code == 302
    assert completed.headers["Location"].endswith("/accounts/login/?reset=1")
    target.refresh_from_db()
    assert target.check_password("Changed-password-2!")
    assert not LoginSession.objects.filter(
        account=target, revoked_at__isnull=True
    ).exists()
    first_session.refresh_from_db()
    second_session.refresh_from_db()
    reset.refresh_from_db()
    assert first_session.revoked_at is not None
    assert second_session.revoked_at is not None
    assert reset.consumed_at is not None
    assert SecurityEvent.objects.filter(
        account=target,
        event_type="ADMIN_PASSWORD_RESET_LINK_COMPLETED",
    ).exists()

    replay = visitor.post(
        reverse("accounts:admin-password-reset"),
        {
            "token": reset_link,
            "new_password": "Another-password-3!",
            "confirm_password": "Another-password-3!",
        },
    )
    assert replay.status_code == 422
    target.refresh_from_db()
    assert target.check_password("Changed-password-2!")

    audits = search_audit(
        action="accounts.password_reset.link.request",
        target_id=str(target.pk),
        is_admin=True,
    )
    assert len(audits) == 1
    audit = audit_detail(entry_id=audits[0].id, is_admin=True)
    assert reset_link not in str((audit.before_safe, audit.after_safe))


def test_expired_and_superseded_links_cannot_change_password(mailpit) -> None:
    admin = bootstrap_test_administrator()
    target = Account.objects.create_account(
        email="reset-link-expired@kaj.test", password="Initial-password-1!"
    )
    admin_client = _client_for(admin)
    visitor = Client(REMOTE_ADDR="127.0.0.1")

    _request_reset(admin_client, target)
    previous_link = _password_reset_token(mailpit)

    _request_reset(admin_client, target)
    issued_tokens = _password_reset_tokens(mailpit)
    assert len(issued_tokens) == 2
    replacement_link = next(token for token in issued_tokens if token != previous_link)
    superseded_response = visitor.post(
        reverse("accounts:admin-password-reset"),
        {
            "token": previous_link,
            "new_password": "Changed-password-2!",
            "confirm_password": "Changed-password-2!",
        },
    )
    assert superseded_response.status_code == 422

    success = visitor.post(
        reverse("accounts:admin-password-reset"),
        {
            "token": replacement_link,
            "new_password": "Changed-password-2!",
            "confirm_password": "Changed-password-2!",
        },
    )
    assert success.status_code == 302
    target.refresh_from_db()
    assert target.check_password("Changed-password-2!")


def test_expired_link_cannot_change_password(mailpit) -> None:
    admin = bootstrap_test_administrator()
    target = Account.objects.create_account(
        email="reset-link-expired@kaj.test", password="Initial-password-1!"
    )
    admin_client = _client_for(admin)
    _request_reset(admin_client, target)
    link = _password_reset_token(mailpit)
    reset = AdminPasswordReset.objects.get(account=target)
    reset.expires_at = timezone.now() - timedelta(seconds=1)
    reset.created_at = reset.expires_at - timedelta(minutes=30)
    reset.save(update_fields=("created_at", "expires_at"))

    response = Client(REMOTE_ADDR="127.0.0.1").post(
        reverse("accounts:admin-password-reset"),
        {
            "token": link,
            "new_password": "Changed-password-2!",
            "confirm_password": "Changed-password-2!",
        },
    )
    assert response.status_code == 422
    target.refresh_from_db()
    assert target.check_password("Initial-password-1!")


def test_password_change_invalidates_link_and_non_admin_cannot_issue(mailpit) -> None:
    admin = bootstrap_test_administrator()
    target = Account.objects.create_account(
        email="reset-link-password-change@kaj.test",
        password="Initial-password-1!",
    )
    admin_client = _client_for(admin)
    _request_reset(admin_client, target)
    link = _password_reset_token(mailpit)

    target.set_password("Changed-outside-link-2!")
    target.save(update_fields=("password_hash", "updated_at"))
    visitor = Client(REMOTE_ADDR="127.0.0.1")
    response = visitor.post(
        reverse("accounts:admin-password-reset"),
        {
            "token": link,
            "new_password": "Changed-password-3!",
            "confirm_password": "Changed-password-3!",
        },
    )
    assert response.status_code == 422
    target.refresh_from_db()
    assert target.check_password("Changed-outside-link-2!")

    ordinary = Account.objects.create_account(
        email="reset-link-member@kaj.test", password="Initial-password-1!"
    )
    with pytest.raises(PermissionError):
        issue_admin_password_reset_link(
            actor_id=ordinary.pk,
            account_id=target.pk,
            client_ip="127.0.0.1",
            trace_code="KJ-RESET-NONADMIN",
            audit_writer=record_audit_entry,
        )
