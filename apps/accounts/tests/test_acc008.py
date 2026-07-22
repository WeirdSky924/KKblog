import pytest
from django.conf import settings
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.middleware import AccountSessionMiddleware
from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.accounts.presentation.views import sessions_view
from apps.accounts.queries.sessions import session_list
from apps.accounts.services.sessions import (
    SessionError,
    revoke_all_sessions,
    revoke_session,
    summarize_user_agent,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def account():
    return Account.objects.create_account(
        email="sessions@kaj.test", password="Session-password-1!"
    )


def test_session_list_is_owned_active_masked_and_marks_current(account) -> None:
    _, current = LoginSession.issue(
        account=account,
        remember=False,
        client_ip="203.0.113.41",
        user_agent_summary="Chrome · Linux",
    )
    _, other = LoginSession.issue(
        account=account,
        remember=True,
        client_ip="2001:db8::41",
        user_agent_summary="Safari · iPhone",
    )
    _, revoked = LoginSession.issue(account=account, remember=False)
    revoked.revoked_at = timezone.now()
    revoked.save(update_fields=("revoked_at",))
    stranger = Account.objects.create_account(
        email="stranger-sessions@kaj.test", password="Stranger-password-1!"
    )
    LoginSession.issue(account=stranger, remember=False)

    items = session_list(account_id=account.id, current_session_id=current.id)

    assert {item.id for item in items} == {current.id, other.id}
    assert next(item for item in items if item.id == current.id).is_current
    assert next(item for item in items if item.id == current.id).masked_ip.endswith(
        ".x"
    )
    assert next(item for item in items if item.id == other.id).masked_ip.endswith("/64")


def test_targeted_revoke_enforces_ownership_and_is_idempotent(account) -> None:
    _, current = LoginSession.issue(account=account, remember=False)
    _, target = LoginSession.issue(account=account, remember=False)
    stranger = Account.objects.create_account(
        email="other-owner@kaj.test", password="Other-password-1!"
    )
    _, stranger_session = LoginSession.issue(account=stranger, remember=False)

    with pytest.raises(SessionError):
        revoke_session(
            account_id=account.id,
            current_session_id=current.id,
            target_session_id=stranger_session.id,
            client_ip="203.0.113.42",
            trace_code="KJ-SESSION-OWNERSHIP",
        )

    assert (
        revoke_session(
            account_id=account.id,
            current_session_id=current.id,
            target_session_id=target.id,
            client_ip="203.0.113.42",
            trace_code="KJ-SESSION-REVOKE",
        )
        == 1
    )
    assert (
        revoke_session(
            account_id=account.id,
            current_session_id=current.id,
            target_session_id=target.id,
            client_ip="203.0.113.42",
            trace_code="KJ-SESSION-REPEAT",
        )
        == 0
    )


def test_revoke_all_includes_current_session(account) -> None:
    _, current = LoginSession.issue(account=account, remember=False)
    LoginSession.issue(account=account, remember=True)

    assert (
        revoke_all_sessions(
            account_id=account.id,
            current_session_id=current.id,
            client_ip="203.0.113.43",
            trace_code="KJ-SESSION-ALL",
        )
        == 2
    )
    assert not LoginSession.objects.filter(
        account=account, revoked_at__isnull=True
    ).exists()


def test_session_view_requires_explicit_all_devices_confirmation(
    client, account
) -> None:
    raw_token, current = LoginSession.issue(account=account, remember=False)
    LoginSession.issue(account=account, remember=True)
    client.cookies["kaj_session"] = raw_token

    response = client.post("/accounts/sessions/", {"action": "revoke_all"})

    assert response.status_code == 422
    assert (
        LoginSession.objects.filter(account=account, revoked_at__isnull=True).count()
        == 2
    )

    response = client.post(
        "/accounts/sessions/",
        {"action": "revoke_all", "confirm": "all_devices"},
    )

    assert response.status_code == 302
    assert response.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME]["max-age"] == 0
    current.refresh_from_db()
    assert current.revoked_at is not None


def test_current_session_revoke_deletes_cookie_and_invalid_id_is_visible(
    client, account
) -> None:
    raw_token, current = LoginSession.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token

    invalid = client.post(
        "/accounts/sessions/",
        {"action": "revoke", "session_id": "not-a-session"},
    )

    assert invalid.status_code == 422
    assert "UUID" in invalid.content.decode()
    assert current.is_active()

    response = client.post(
        "/accounts/sessions/",
        {"action": "revoke", "session_id": str(current.id)},
    )

    assert response.status_code == 302
    assert response.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME]["max-age"] == 0
    current.refresh_from_db()
    assert current.revoked_at is not None


@pytest.mark.parametrize("role", [None, "AUTHOR", "ADMINISTRATOR"])
def test_session_page_accepts_each_authenticated_role(client, account, role) -> None:
    if role == RoleAssignment.Role.AUTHOR:
        RoleAssignment.objects.create(account=account, role=role)
    elif role == RoleAssignment.Role.ADMINISTRATOR:
        RoleAssignment.objects.create(account=account, role=RoleAssignment.Role.AUTHOR)
        RoleAssignment.objects.create(account=account, role=role)
    raw_token, _ = LoginSession.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token

    response = client.get("/accounts/sessions/")

    assert response.status_code == 200
    assert "当前设备" in response.content.decode()


def test_disabled_account_is_not_authorized_and_cookie_is_deleted(
    client, account
) -> None:
    raw_token, _ = LoginSession.issue(account=account, remember=False)
    account.status = Account.Status.DISABLED
    account.save(update_fields=("status", "updated_at"))
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token

    response = client.get("/accounts/sessions/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    assert response.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME]["max-age"] == 0


def test_session_page_has_recovery_empty_state_after_concurrent_revocation(
    account,
) -> None:
    raw_token, current = LoginSession.issue(account=account, remember=False)
    request = RequestFactory().get(
        "/accounts/sessions/",
        HTTP_COOKIE=f"{settings.ACCOUNT_SESSION_COOKIE_NAME}={raw_token}",
    )

    def revoke_between_authentication_and_query(authenticated_request):
        LoginSession.objects.filter(pk=current.id).delete()
        return sessions_view(authenticated_request)

    response = AccountSessionMiddleware(revoke_between_authentication_and_query)(
        request
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "没有可用会话" in body
    assert "重新登录" in body


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Mozilla/5.0 (X11; Linux x86_64) Chrome/125.0 Safari/537.36",
            "Chrome · Linux",
        ),
        (
            "Mozilla/5.0 (iPhone) AppleWebKit/605.1 Version/17.0 Mobile Safari/604.1",
            "Safari · iPhone",
        ),
        ("", "未知浏览器 · 未知设备"),
    ],
)
def test_user_agent_summary_is_bounded(raw, expected) -> None:
    assert summarize_user_agent(raw) == expected
