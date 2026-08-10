import pytest

from apps.accounts.models import Account, InviteCode, LoginSession
from apps.accounts.policies.registration import RegistrationPolicy
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.invites import generate_invite_codes
from apps.accounts.services.registration import (
    RegistrationError,
    register_account,
    request_registration_code,
)
from apps.accounts.services.verification import VerificationStore

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def store(isolated_redis):
    client, prefix = isolated_redis
    return VerificationStore(client=client, namespace=prefix.rstrip(":"))


@pytest.fixture
def invite():
    admin = bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="One-time-password-1!",
        production=False,
    )
    return generate_invite_codes(
        count=1,
        validity_days=7,
        actor_id=admin.id,
        trace_code="KJ-REG-INVITE",
        client_ip="127.0.0.1",
        audit_writer=lambda **kwargs: kwargs,
    )[0]


def request_code(*, store, mailpit, email, policy, invite_code="", code="123456"):
    request_registration_code(
        email=email,
        invite_code=invite_code,
        policy=policy,
        client_ip="203.0.113.10",
        trace_code="KJ-REG-SEND",
        store=store,
        code_generator=lambda: code,
    )


def test_closed_direct_registration_still_accepts_invite(
    store, mailpit, invite
) -> None:
    closed = RegistrationPolicy(direct_enabled=False)
    with pytest.raises(RegistrationError):
        request_code(
            store=store,
            mailpit=mailpit,
            email="direct@kaj.test",
            policy=closed,
        )
    request_code(
        store=store,
        mailpit=mailpit,
        email="invited@kaj.test",
        policy=closed,
        invite_code=invite.raw_code,
    )
    result = register_account(
        email="invited@kaj.test",
        code="123456",
        password="Valid-password-1",
        invite_code=invite.raw_code,
        remember=False,
        policy=closed,
        client_ip="203.0.113.10",
        trace_code="KJ-REG-DONE",
        store=store,
    )
    assert result.account.email == "invited@kaj.test"
    assert result.session.kind == LoginSession.Kind.STANDARD_12H
    assert InviteCode.objects.get(pk=invite.id).redeemed_by_id == result.account.id


def test_open_direct_registration_creates_remembered_session(store, mailpit) -> None:
    open_policy = RegistrationPolicy(direct_enabled=True)
    request_code(
        store=store,
        mailpit=mailpit,
        email="direct@kaj.test",
        policy=open_policy,
    )
    result = register_account(
        email="direct@kaj.test",
        nickname="Kaj_01!",
        code="123456",
        password="Valid-password-1",
        invite_code="",
        remember=True,
        policy=open_policy,
        client_ip="203.0.113.11",
        trace_code="KJ-REG-DIRECT",
        store=store,
    )
    result.account.refresh_from_db()
    assert result.account.nickname == "Kaj_01!"
    assert result.account.normalized_nickname == "kaj_01!"
    assert result.session.kind == LoginSession.Kind.REMEMBER_30D
    assert result.raw_session_token not in result.session.token_digest


def test_registration_rejects_invalid_nickname_before_creating_account(
    store, mailpit
) -> None:
    open_policy = RegistrationPolicy(direct_enabled=True)
    request_code(
        store=store,
        mailpit=mailpit,
        email="invalid-nickname@kaj.test",
        policy=open_policy,
    )

    with pytest.raises(RegistrationError):
        register_account(
            email="invalid-nickname@kaj.test",
            nickname="Bad Name",
            code="123456",
            password="Valid-password-1",
            invite_code="",
            remember=False,
            policy=open_policy,
            client_ip="203.0.113.11",
            trace_code="KJ-REG-NICKNAME",
            store=store,
        )

    assert not Account.objects.filter(email="invalid-nickname@kaj.test").exists()


def test_unique_conflict_does_not_consume_invite(store, mailpit, invite) -> None:
    Account.objects.create_account(email="taken@kaj.test", password="Other-password-1")
    policy = RegistrationPolicy(direct_enabled=False)
    request_code(
        store=store,
        mailpit=mailpit,
        email="taken@kaj.test",
        policy=policy,
        invite_code=invite.raw_code,
    )
    with pytest.raises(RegistrationError):
        register_account(
            email="taken@kaj.test",
            code="123456",
            password="Valid-password-1",
            invite_code=invite.raw_code,
            remember=False,
            policy=policy,
            client_ip="203.0.113.12",
            trace_code="KJ-REG-CONFLICT",
            store=store,
        )
    assert InviteCode.objects.get(pk=invite.id).state() == "ACTIVE"


def test_invite_and_code_bind_to_original_email(store, mailpit, invite) -> None:
    policy = RegistrationPolicy(direct_enabled=False)
    request_code(
        store=store,
        mailpit=mailpit,
        email="bound@kaj.test",
        policy=policy,
        invite_code=invite.raw_code,
    )
    with pytest.raises(RegistrationError):
        register_account(
            email="other@kaj.test",
            code="123456",
            password="Valid-password-1",
            invite_code=invite.raw_code,
            remember=False,
            policy=policy,
            client_ip="203.0.113.13",
            trace_code="KJ-REG-BOUND",
            store=store,
        )
    assert InviteCode.objects.get(pk=invite.id).state() == "ACTIVE"
