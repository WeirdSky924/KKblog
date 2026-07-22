from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections

from apps.accounts.models import Account, LoginSession
from apps.accounts.models.session import session_token_digest
from apps.accounts.services.credentials import (
    CredentialError,
    change_email,
    change_password,
    request_new_email_code,
    request_password_reset_code,
    reset_password,
)
from apps.accounts.services.verification import VerificationStore

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def account():
    return Account.objects.create_account(
        email="credentials@kaj.test", password="Old-password-1!"
    )


@pytest.fixture
def store(isolated_redis):
    client, prefix = isolated_redis
    return VerificationStore(client=client, namespace=prefix.rstrip(":"))


def test_password_reset_revokes_every_session(account, store, mailpit) -> None:
    LoginSession.issue(account=account, remember=False)
    LoginSession.issue(account=account, remember=True)
    request_password_reset_code(
        email=account.email,
        client_ip="203.0.113.30",
        trace_code="KJ-RESET-SEND",
        store=store,
        code_generator=lambda: "111222",
    )
    reset_password(
        email=account.email,
        code="111222",
        new_password="New-password-2!",
        client_ip="203.0.113.30",
        trace_code="KJ-RESET-DONE",
        store=store,
    )
    account.refresh_from_db()
    assert account.check_password("New-password-2!")
    assert not LoginSession.objects.filter(
        account=account, revoked_at__isnull=True
    ).exists()


def test_logged_in_change_password_rotates_current_and_revokes_others(account) -> None:
    current_raw, current = LoginSession.issue(account=account, remember=False)
    _, other = LoginSession.issue(account=account, remember=True)
    result = change_password(
        account_id=account.id,
        current_session_id=current.id,
        current_password="Old-password-1!",
        new_password="New-password-2!",
        client_ip="203.0.113.31",
        trace_code="KJ-CHANGE-PASSWORD",
    )
    current.refresh_from_db()
    other.refresh_from_db()
    account.refresh_from_db()
    assert current.token_digest == session_token_digest(result.raw_token)
    assert current.token_digest != session_token_digest(current_raw)
    assert result.raw_token != current_raw
    assert other.revoked_at is not None
    assert current.revoked_at is None
    assert account.check_password("New-password-2!")


def test_change_email_needs_only_new_email_code_and_rotates_current(
    account, store, mailpit
) -> None:
    current_raw, current = LoginSession.issue(account=account, remember=False)
    _, other = LoginSession.issue(account=account, remember=True)
    request_new_email_code(
        account_id=account.id,
        new_email="new-address@kaj.test",
        client_ip="203.0.113.32",
        trace_code="KJ-EMAIL-SEND",
        store=store,
        code_generator=lambda: "222333",
    )
    result = change_email(
        account_id=account.id,
        current_session_id=current.id,
        new_email="new-address@kaj.test",
        code="222333",
        client_ip="203.0.113.32",
        trace_code="KJ-EMAIL-DONE",
        store=store,
    )
    account.refresh_from_db()
    current.refresh_from_db()
    other.refresh_from_db()
    assert account.email == "new-address@kaj.test"
    assert result.raw_token != current_raw
    assert current.token_digest == session_token_digest(result.raw_token)
    assert current.token_digest != session_token_digest(current_raw)
    assert other.revoked_at is None


def test_change_email_unique_conflict_keeps_old_email(account, store, mailpit) -> None:
    Account.objects.create_account(
        email="occupied@kaj.test", password="Other-password-1!"
    )
    _, current = LoginSession.issue(account=account, remember=False)
    request_new_email_code(
        account_id=account.id,
        new_email="occupied@kaj.test",
        client_ip="203.0.113.33",
        trace_code="KJ-EMAIL-CONFLICT-SEND",
        store=store,
        code_generator=lambda: "333444",
    )
    with pytest.raises(CredentialError):
        change_email(
            account_id=account.id,
            current_session_id=current.id,
            new_email="occupied@kaj.test",
            code="333444",
            client_ip="203.0.113.33",
            trace_code="KJ-EMAIL-CONFLICT",
            store=store,
        )
    account.refresh_from_db()
    assert account.email == "credentials@kaj.test"


def test_concurrent_email_change_has_one_database_winner(store, monkeypatch) -> None:
    first = Account.objects.create_account(
        email="first-change@kaj.test", password="First-password-1!"
    )
    second = Account.objects.create_account(
        email="second-change@kaj.test", password="Second-password-1!"
    )
    sessions = {
        first.id: LoginSession.issue(account=first, remember=False)[1].id,
        second.id: LoginSession.issue(account=second, remember=False)[1].id,
    }
    verification_barrier = Barrier(2)

    def synchronized_verification(**_kwargs) -> None:
        verification_barrier.wait(timeout=5)

    monkeypatch.setattr(
        "apps.accounts.services.credentials.verify_code",
        synchronized_verification,
    )

    def attempt(account_id) -> str:
        close_old_connections()
        try:
            change_email(
                account_id=account_id,
                current_session_id=sessions[account_id],
                new_email="one-winner@kaj.test",
                code="123456",
                client_ip="203.0.113.34",
                trace_code="KJ-EMAIL-CONCURRENT",
                store=store,
            )
        except CredentialError:
            return "conflict"
        finally:
            close_old_connections()
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, (first.id, second.id)))

    assert sorted(outcomes) == ["conflict", "success"]
    assert Account.objects.filter(email="one-winner@kaj.test").count() == 1


def test_password_reset_success_is_visible_on_login(client) -> None:
    response = client.get("/accounts/login/?reset=1")
    assert response.status_code == 200
    assert "密码已重置，请使用新密码登录。" in response.content.decode()
