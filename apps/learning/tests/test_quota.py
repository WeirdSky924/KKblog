from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import connections

from apps.learning.public import (
    DEFAULT_CONCURRENT_MODEL_RUNS,
    DEFAULT_DAILY_GENERATIONS,
    DEFAULT_DAILY_UPLOADS,
    DEFAULT_PENDING_REVIEWS,
    DEFAULT_UNPURGED_BANKS,
    LearningCommandError,
    LearningModelRunKind,
    LearningQuotaLimits,
    LearningQuotaOverride,
    configure_account_quota_override,
    configure_site_quota_policy,
    effective_learning_quota,
    release_learning_model_run,
    reserve_learning_model_run,
)

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 17, 5, 0, tzinfo=UTC)


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model = apps.get_model("accounts", "RoleAssignment")
    if author:
        role_model.objects.create(account=account, role="AUTHOR")
        account.attachment_upload_enabled = True
        account.save(update_fields=("attachment_upload_enabled", "updated_at"))
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _limits(**overrides) -> LearningQuotaLimits:
    values = {
        "daily_uploads": DEFAULT_DAILY_UPLOADS,
        "pending_reviews": DEFAULT_PENDING_REVIEWS,
        "daily_generations": DEFAULT_DAILY_GENERATIONS,
        "concurrent_model_runs": DEFAULT_CONCURRENT_MODEL_RUNS,
        "unpurged_banks": DEFAULT_UNPURGED_BANKS,
    }
    values.update(overrides)
    return LearningQuotaLimits(**values)


def test_default_policy_partial_override_and_audit() -> None:
    administrator = _account("quota-admin", administrator=True)
    author = _account("quota-author", author=True)
    policy_model = apps.get_model("learning", "LearningQuotaPolicy")
    audit_model = apps.get_model("operations", "AuditEntry")

    policy = policy_model.objects.get(pk=1)
    assert policy.row_version == 1
    assert effective_learning_quota(author.id) == _limits()

    updated = configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=1,
        limits=_limits(daily_uploads=20, concurrent_model_runs=2),
        trace_code="KJ-LEARNING-QUOTA-SITE",
        client_ip="127.0.0.1",
    )
    assert updated.row_version == 2
    assert effective_learning_quota(author.id).daily_uploads == 20

    override = configure_account_quota_override(
        actor_id=administrator.id,
        account_id=author.id,
        expected_version=0,
        limits=LearningQuotaOverride(
            daily_uploads=3,
            pending_reviews=None,
            daily_generations=None,
            concurrent_model_runs=1,
            unpurged_banks=None,
        ),
        trace_code="KJ-LEARNING-QUOTA-ACCOUNT",
        client_ip="127.0.0.1",
    )
    effective = effective_learning_quota(author.id)
    assert override.row_version == 1
    assert effective.daily_uploads == 3
    assert effective.pending_reviews == DEFAULT_PENDING_REVIEWS
    assert effective.concurrent_model_runs == 1
    assert set(audit_model.objects.values_list("action", flat=True)) == {
        "learning.quota.site.update",
        "learning.quota.account.update",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("daily_uploads", 0),
        ("daily_uploads", 101),
        ("pending_reviews", 21),
        ("daily_generations", 51),
        ("concurrent_model_runs", 4),
        ("unpurged_banks", 2001),
    ],
)
def test_quota_policy_rejects_values_outside_hard_ranges(
    field: str,
    value: int,
) -> None:
    administrator = _account(f"quota-range-{field}", administrator=True)

    with pytest.raises(LearningCommandError) as captured:
        configure_site_quota_policy(
            actor_id=administrator.id,
            expected_version=1,
            limits=_limits(**{field: value}),
            trace_code="KJ-LEARNING-QUOTA-RANGE",
            client_ip="127.0.0.1",
        )
    assert captured.value.code == "learning.quota_invalid.v1"


def test_account_override_requires_current_attachment_capability() -> None:
    administrator = _account("quota-cap-admin", administrator=True)
    target = _account("quota-cap-target")

    with pytest.raises(LearningCommandError) as captured:
        configure_account_quota_override(
            actor_id=administrator.id,
            account_id=target.id,
            expected_version=0,
            limits=LearningQuotaOverride(daily_uploads=2),
            trace_code="KJ-LEARNING-QUOTA-DENIED",
            client_ip="127.0.0.1",
        )
    assert captured.value.code == "learning.attachment_capability_required.v1"


def test_model_run_reservation_is_idempotent_releasable_and_recovers_expiry() -> None:
    owner = _account("quota-reservation", author=True)
    first_ref = str(uuid4())
    second_ref = str(uuid4())

    first = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.REVIEW,
        owner_ref=first_ref,
        idempotency_key=f"review:{first_ref}",
        lease_expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )
    repeated = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.REVIEW,
        owner_ref=first_ref,
        idempotency_key=f"review:{first_ref}",
        lease_expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )
    assert repeated.reservation_id == first.reservation_id

    with pytest.raises(LearningCommandError) as exhausted:
        reserve_learning_model_run(
            account_id=owner.id,
            kind=LearningModelRunKind.GENERATION,
            owner_ref=second_ref,
            idempotency_key=f"generation:{second_ref}",
            lease_expires_at=NOW + timedelta(minutes=5),
            now=NOW,
        )
    assert exhausted.value.code == "learning.concurrent_quota_exhausted.v1"

    released = release_learning_model_run(reservation_id=first.reservation_id)
    assert released.status == "RELEASED"
    state_model = apps.get_model("learning", "LearningAccountQuotaState")
    released_version = state_model.objects.get(account=owner).row_version
    repeated_release = release_learning_model_run(reservation_id=first.reservation_id)
    assert repeated_release.status == "RELEASED"
    assert state_model.objects.get(account=owner).row_version == released_version
    second = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.GENERATION,
        owner_ref=second_ref,
        idempotency_key=f"generation:{second_ref}",
        lease_expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    third_ref = str(uuid4())
    third = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.REVIEW,
        owner_ref=third_ref,
        idempotency_key=f"review:{third_ref}",
        lease_expires_at=NOW + timedelta(minutes=10),
        now=NOW + timedelta(minutes=2),
    )
    reservation_model = apps.get_model("learning", "LearningModelRunReservation")
    assert reservation_model.objects.get(pk=second.reservation_id).status == "EXPIRED"
    assert third.status == "ACTIVE"


def test_concurrent_model_run_claims_allow_only_configured_limit() -> None:
    owner = _account("quota-concurrent", author=True)

    def worker(index: int) -> str:
        connections.close_all()
        owner_ref = str(uuid4())
        try:
            reserve_learning_model_run(
                account_id=owner.id,
                kind=LearningModelRunKind.REVIEW,
                owner_ref=owner_ref,
                idempotency_key=f"concurrent:{index}:{owner_ref}",
                lease_expires_at=NOW + timedelta(minutes=5),
                now=NOW,
            )
        except LearningCommandError as exc:
            return exc.code
        finally:
            connections.close_all()
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))
    assert sorted(outcomes) == sorted(
        ["reserved", "learning.concurrent_quota_exhausted.v1"]
    )


def test_expired_reservations_stay_recovered_when_lower_limit_rejects_new_run() -> None:
    administrator = _account("quota-expiry-admin", administrator=True)
    owner = _account("quota-expiry-owner", author=True)
    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=1,
        limits=_limits(concurrent_model_runs=2),
        trace_code="KJ-LEARNING-EXPIRY-UP",
        client_ip="127.0.0.1",
    )
    first_ref = str(uuid4())
    second_ref = str(uuid4())
    first = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.REVIEW,
        owner_ref=first_ref,
        idempotency_key=f"expiry:{first_ref}",
        lease_expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    second = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.GENERATION,
        owner_ref=second_ref,
        idempotency_key=f"expiry:{second_ref}",
        lease_expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    configure_site_quota_policy(
        actor_id=administrator.id,
        expected_version=2,
        limits=_limits(concurrent_model_runs=1),
        trace_code="KJ-LEARNING-EXPIRY-DOWN",
        client_ip="127.0.0.1",
    )

    third_ref = str(uuid4())
    with pytest.raises(LearningCommandError) as exhausted:
        reserve_learning_model_run(
            account_id=owner.id,
            kind=LearningModelRunKind.REVIEW,
            owner_ref=third_ref,
            idempotency_key=f"expiry:{third_ref}",
            lease_expires_at=NOW + timedelta(minutes=20),
            now=NOW + timedelta(minutes=2),
        )
    assert exhausted.value.code == "learning.concurrent_quota_exhausted.v1"
    reservation_model = apps.get_model("learning", "LearningModelRunReservation")
    state_model = apps.get_model("learning", "LearningAccountQuotaState")
    assert reservation_model.objects.get(pk=first.reservation_id).status == "EXPIRED"
    assert reservation_model.objects.get(pk=second.reservation_id).status == "ACTIVE"
    assert state_model.objects.get(account=owner).active_model_runs == 1
