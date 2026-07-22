import threading

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections

from apps.accounts.models import Account, LoginSession, RoleAssignment
from apps.accounts.services.bootstrap import (
    BootstrapError,
    bootstrap_administrator,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_account_normalizes_email_and_unicode_casefold_nickname() -> None:
    first = Account.objects.create_account(
        email="Person@KAJ.TEST",
        password="Valid-password-1",
        nickname="Kaj",
    )
    assert first.email == "person@kaj.test"
    assert first.nickname == "Kaj"
    assert first.normalized_nickname == "kaj"

    with pytest.raises(IntegrityError):
        Account.objects.create_account(
            email="other@kaj.test",
            password="Valid-password-2",
            nickname="KAJ",
        )


def test_account_email_is_case_insensitively_unique() -> None:
    Account.objects.create_account(email="User@kaj.test", password="Valid-password-1")
    with pytest.raises(IntegrityError):
        Account.objects.create_account(
            email="user@KAJ.TEST",
            password="Valid-password-2",
        )


def test_admin_role_is_unique_and_admin_must_remain_author() -> None:
    admin = bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="One-time-password-1!",
        production=False,
    )
    assert admin.must_change_password is True
    assert set(admin.roles.values_list("role", flat=True)) == {
        RoleAssignment.Role.ADMINISTRATOR,
        RoleAssignment.Role.AUTHOR,
    }
    other = Account.objects.create_account(
        email="other@kaj.test",
        password="Valid-password-2",
    )
    with pytest.raises(IntegrityError):
        RoleAssignment.objects.create(
            account=other,
            role=RoleAssignment.Role.ADMINISTRATOR,
        )
    with pytest.raises(ValidationError):
        admin.roles.get(role=RoleAssignment.Role.AUTHOR).delete()
    with pytest.raises(ValidationError):
        admin.delete()


def test_bootstrap_secret_is_single_use_and_not_stored() -> None:
    bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="One-time-password-1!",
        production=False,
    )
    with pytest.raises(BootstrapError):
        bootstrap_administrator(
            email="admin@kaj.test",
            initial_password="Different-password-2!",
            production=False,
        )
    assert not Account.objects.filter(password_hash="One-time-password-1!").exists()


def test_production_rejects_missing_or_test_admin_identity() -> None:
    for email in ("", "admin@kaj.test"):
        with pytest.raises(BootstrapError):
            bootstrap_administrator(
                email=email,
                initial_password="One-time-password-1!",
                production=True,
            )


def test_login_session_persists_only_token_digest() -> None:
    account = Account.objects.create_account(
        email="session@kaj.test", password="Valid-password-1"
    )
    raw_token, session = LoginSession.issue(account=account, remember=False)
    assert len(raw_token) >= 43
    assert raw_token not in session.token_digest
    assert session.is_active()


def test_casefold_concurrency_has_one_winner(django_db_blocker) -> None:
    barrier = threading.Barrier(2)
    results = []

    def create(email: str, nickname: str) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            Account.objects.create_account(
                email=email,
                password="Valid-password-1",
                nickname=nickname,
            )
        except IntegrityError:
            results.append("conflict")
        else:
            results.append("created")
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=create, args=("one@kaj.test", "Straße")),
        threading.Thread(target=create, args=("two@kaj.test", "STRASSE")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(results) == ["conflict", "created"]
