from datetime import timedelta

import pytest
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.accounts.middleware import AccountSessionMiddleware
from apps.accounts.models import Account, LoginSession
from apps.accounts.services.authentication import (
    AuthenticationError,
    authenticate_code,
    authenticate_password,
    request_login_code,
)
from apps.accounts.services.verification import VerificationStore

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def account():
    return Account.objects.create_account(
        email="login@kaj.test", password="Valid-password-1"
    )


@pytest.fixture
def store(isolated_redis):
    client, prefix = isolated_redis
    return VerificationStore(client=client, namespace=prefix.rstrip(":"))


def test_password_login_issues_12h_or_30d_digest_only(account) -> None:
    normal = authenticate_password(
        email=account.email,
        password="Valid-password-1",
        remember=False,
        client_ip="203.0.113.20",
        trace_code="KJ-LOGIN-12H",
    )
    remembered = authenticate_password(
        email=account.email,
        password="Valid-password-1",
        remember=True,
        client_ip="203.0.113.20",
        trace_code="KJ-LOGIN-30D",
    )
    assert normal.session.expires_at - normal.session.created_at == timedelta(hours=12)
    assert remembered.session.expires_at - remembered.session.created_at == timedelta(
        days=30
    )
    assert normal.raw_token not in normal.session.token_digest


def test_email_code_login_and_purpose(account, store, mailpit) -> None:
    request_login_code(
        email=account.email,
        client_ip="203.0.113.21",
        trace_code="KJ-LOGIN-SEND",
        store=store,
        code_generator=lambda: "876543",
    )
    result = authenticate_code(
        email=account.email,
        code="876543",
        remember=False,
        client_ip="203.0.113.21",
        trace_code="KJ-LOGIN-CODE",
        store=store,
        user_agent_summary="Firefox · Linux",
    )
    assert result.session.user_agent_summary == "Firefox · Linux"
    assert result.account.id == account.id
    with pytest.raises(AuthenticationError):
        authenticate_code(
            email=account.email,
            code="876543",
            remember=False,
            client_ip="203.0.113.21",
            trace_code="KJ-LOGIN-REPLAY",
            store=store,
        )


def test_middleware_rejects_expired_revoked_and_disabled_sessions(account) -> None:
    raw, session = LoginSession.issue(account=account, remember=False)

    def response(request):
        return request.account_id

    middleware = AccountSessionMiddleware(response)
    request = RequestFactory().get("/", HTTP_COOKIE=f"kaj_session={raw}")
    request.COOKIES["kaj_session"] = raw
    assert middleware(request) == account.id

    session.created_at = timezone.now() - timedelta(hours=13)
    session.last_seen_at = session.created_at
    session.expires_at = timezone.now() - timedelta(hours=1)
    session.save(update_fields=["created_at", "last_seen_at", "expires_at"])
    request = RequestFactory().get("/")
    request.COOKIES["kaj_session"] = raw
    assert middleware(request) is None

    raw, session = LoginSession.issue(account=account, remember=False)
    account.status = Account.Status.DISABLED
    account.save(update_fields=["status", "updated_at"])
    request = RequestFactory().get("/")
    request.COOKIES["kaj_session"] = raw
    assert middleware(request) is None


def test_login_view_tabs_cookie_flags_and_safe_return(account) -> None:
    client = Client()
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    assert "密码登录" in response.content.decode()
    assert "邮箱验证码" in response.content.decode()
    response = client.post(
        "/accounts/login/?next=/accounts/sessions/",
        {
            "action": "password",
            "email": account.email,
            "password": "Valid-password-1",
            "remember": "on",
        },
    )
    assert response.status_code == 302
    assert response["Location"] == "/accounts/sessions/"
    cookie = response.cookies["kaj_session"]
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"] == "Lax"


def test_disabled_account_uses_generic_message(account) -> None:
    account.status = Account.Status.DISABLED
    account.save(update_fields=["status", "updated_at"])
    with pytest.raises(AuthenticationError, match="账号当前不可登录"):
        authenticate_password(
            email=account.email,
            password="Valid-password-1",
            remember=False,
            client_ip="203.0.113.22",
            trace_code="KJ-LOGIN-DISABLED",
        )
