import threading
from datetime import timedelta

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.accounts.models import Account, InviteCode
from apps.accounts.services.bootstrap import bootstrap_administrator
from apps.accounts.services.invites import (
    InviteError,
    generate_invite_codes,
    redeem_invite,
    revoke_invites,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def admin():
    return bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="One-time-password-1!",
        production=False,
    )


def audit_ok(**kwargs):
    return kwargs


def test_batch_limits_and_raw_codes_are_returned_once(admin) -> None:
    with pytest.raises(InviteError):
        generate_invite_codes(
            count=1001,
            validity_days=7,
            actor_id=admin.id,
            trace_code="KJ-INVITE-LIMIT",
            client_ip="127.0.0.1",
            audit_writer=audit_ok,
        )
    result = generate_invite_codes(
        count=3,
        validity_days=7,
        actor_id=admin.id,
        trace_code="KJ-INVITE-GEN",
        client_ip="127.0.0.1",
        audit_writer=audit_ok,
    )
    assert len(result) == 3
    assert all(len(item.raw_code) == 16 for item in result)
    assert set("".join(item.raw_code for item in result)) <= set(
        "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    )
    assert not hasattr(InviteCode.objects.first(), "raw_code")
    assert not InviteCode.objects.filter(code_digest=result[0].raw_code).exists()


def test_expiry_boundary_and_used_code_cannot_be_revoked(admin) -> None:
    now = timezone.now()
    issued = generate_invite_codes(
        count=1,
        validity_days=1,
        actor_id=admin.id,
        trace_code="KJ-INVITE-EXP",
        client_ip="127.0.0.1",
        audit_writer=audit_ok,
        now=now,
    )[0]
    invite = InviteCode.objects.get(pk=issued.id)
    assert (
        invite.state(now=now + timedelta(days=1) - timedelta(microseconds=1))
        == "ACTIVE"
    )
    assert invite.state(now=now + timedelta(days=1)) == "EXPIRED"

    account = Account.objects.create_account(
        email="used@kaj.test", password="Valid-password-1"
    )
    redeem_invite(raw_code=issued.raw_code, account_id=account.id, now=now)
    with pytest.raises(InviteError):
        revoke_invites(
            invite_ids=[issued.id],
            actor_id=admin.id,
            trace_code="KJ-INVITE-REVOKE",
            client_ip="127.0.0.1",
            audit_writer=audit_ok,
            now=now,
        )


def test_audit_failure_rolls_back_generation(admin) -> None:
    def fail_audit(**kwargs):
        raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError):
        generate_invite_codes(
            count=2,
            validity_days=3,
            actor_id=admin.id,
            trace_code="KJ-INVITE-ROLLBACK",
            client_ip="127.0.0.1",
            audit_writer=fail_audit,
        )
    assert InviteCode.objects.count() == 0


def test_same_code_concurrent_redemption_has_one_winner(admin) -> None:
    issued = generate_invite_codes(
        count=1,
        validity_days=7,
        actor_id=admin.id,
        trace_code="KJ-INVITE-CONCURRENT",
        client_ip="127.0.0.1",
        audit_writer=audit_ok,
    )[0]
    accounts = [
        Account.objects.create_account(
            email=f"winner-{number}@kaj.test", password="Valid-password-1"
        )
        for number in range(2)
    ]
    barrier = threading.Barrier(2)
    results = []

    def redeem(account_id) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            redeem_invite(raw_code=issued.raw_code, account_id=account_id)
        except InviteError:
            results.append("rejected")
        else:
            results.append("redeemed")
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=redeem, args=(account.id,)) for account in accounts
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(results) == ["redeemed", "rejected"]
    assert InviteCode.objects.get(pk=issued.id).redeemed_by_id in {
        account.id for account in accounts
    }
