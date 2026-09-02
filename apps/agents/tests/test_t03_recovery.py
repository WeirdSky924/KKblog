from datetime import timedelta

import pytest

from apps.agents.models import AgentInvocation, AgentTokenLedger, AgentTokenReservation
from apps.agents.providers.fake import DeterministicFakeProviderTransport
from apps.agents.public import (
    create_agent_invocation,
    recover_expired_token_reservations,
    reserve_invocation_tokens,
)
from apps.agents.services.runtime import mark_invocation_running
from apps.agents.tests.test_t03_gateway import (
    NOW,
    _configured_invocation,
    _gateway,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_endpoint_concurrency_limit_blocks_before_external_call() -> None:
    _, _, profile, first = _configured_invocation(caller_id="concurrency-first")
    reserve_invocation_tokens(
        invocation_id=first.id,
        requested_tokens=first.per_run_token_limit_snapshot,
        idempotency_key="reserve-concurrency-first",
        lease_expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )
    second = create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id="concurrency-second",
        idempotency_key="review-concurrency-second",
        estimated_input_tokens=1_000,
    )
    transport = DeterministicFakeProviderTransport(value={"verdict": "APPROVED"})
    with pytest.raises(Exception) as rejected:
        _gateway(transport).execute(
            invocation_id=second.id,
            input_blocks=("资料",),
            now=NOW,
        )
    assert getattr(rejected.value, "code", None) == "agents.concurrency_exhausted.v1"
    assert transport.call_count == 0
    second.refresh_from_db()
    assert second.state == AgentInvocation.State.PENDING


def test_recovery_does_not_charge_expired_running_invocation() -> None:
    _, _, _, invocation = _configured_invocation(caller_id="lease-running")
    reservation = reserve_invocation_tokens(
        invocation_id=invocation.id,
        requested_tokens=invocation.per_run_token_limit_snapshot,
        idempotency_key="reserve-lease-running",
        lease_expires_at=NOW + timedelta(seconds=30),
        now=NOW,
    )
    mark_invocation_running(
        invocation_id=invocation.id,
        started_at=NOW,
        input_sha256="a" * 64,
    )

    result = recover_expired_token_reservations(
        now=NOW + timedelta(seconds=31), batch_size=10
    )
    assert result.conservative_count == 0
    assert result.released_count == 0
    reservation.refresh_from_db()
    invocation.refresh_from_db()
    assert reservation.status == AgentTokenReservation.Status.EXPIRED
    assert reservation.settled_tokens == 0
    assert invocation.state == AgentInvocation.State.FAILED
    assert invocation.safe_error_code == "agents.invocation_lease_expired.v1"
    assert set(AgentTokenLedger.objects.values_list("settled_tokens", flat=True)) == {0}

    repeated = recover_expired_token_reservations(
        now=NOW + timedelta(minutes=10), batch_size=10
    )
    assert repeated.conservative_count == 0
    assert repeated.released_count == 0


def test_recovery_releases_preflight_reservation_without_usage() -> None:
    _, _, _, invocation = _configured_invocation(caller_id="lease-pending")
    reservation = reserve_invocation_tokens(
        invocation_id=invocation.id,
        requested_tokens=invocation.per_run_token_limit_snapshot,
        idempotency_key="reserve-lease-pending",
        lease_expires_at=NOW + timedelta(seconds=30),
        now=NOW,
    )

    result = recover_expired_token_reservations(
        now=NOW + timedelta(seconds=31), batch_size=10
    )
    assert result.released_count == 1
    assert result.conservative_count == 0
    reservation.refresh_from_db()
    invocation.refresh_from_db()
    assert reservation.status == AgentTokenReservation.Status.RELEASED
    assert reservation.settled_tokens == 0
    assert invocation.state == AgentInvocation.State.FAILED
    assert invocation.safe_error_code == "agents.invocation_lease_expired.v1"
    assert set(AgentTokenLedger.objects.values_list("settled_tokens", flat=True)) == {0}
