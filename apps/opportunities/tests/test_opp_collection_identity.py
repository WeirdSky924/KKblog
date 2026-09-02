from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.accounts.models import Account, RoleAssignment
from apps.core.observability.trace import new_trace_code
from apps.opportunities.checks.adapters import AdapterResult, CollectedOpportunity
from apps.opportunities.models import (
    Opportunity,
    OpportunityCheck,
    OpportunityFilterKind,
    OpportunitySource,
    OpportunitySourceFilterOption,
)
from apps.opportunities.public import SourceDraft, create_source
from apps.opportunities.services.collection import (
    CollectionApplyResult,
    CollectionRejected,
    apply_adapter_result,
    record_collection_snapshot,
    validate_adapter_result,
)
from apps.opportunities.services.runner import _listing_opportunity_success

pytestmark = pytest.mark.django_db

OBSERVED_AT = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
LIST_URL = "https://jobs.example.com/campus/jobs"


def _source() -> OpportunitySource:
    account = Account.objects.create_account(
        email=f"opp-identity-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    result = create_source(
        actor_id=account.id,
        draft=SourceDraft(
            company_name="示例科技",
            source_type="CAMPUS",
            official_url="https://jobs.example.com/campus",
            note="公开招聘入口",
            adapter_key="example-v1",
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    return OpportunitySource.objects.get(pk=result.source_id)


def _candidate(title: str) -> CollectedOpportunity:
    return CollectedOpportunity(
        title=title,
        target_url=LIST_URL,
        recruitment_type=Opportunity.RecruitmentType.CAMPUS,
        plan="2027 届校园招聘",
        location_text="杭州",
        category_labels=("研发",),
        city_labels=("杭州",),
        cohort_labels=("2027届",),
    )


def _result(*titles: str) -> AdapterResult:
    return AdapterResult(
        complete=True,
        opportunities=tuple(_candidate(title) for title in titles),
        category_labels=("研发",),
        city_labels=("杭州",),
        cohort_labels=("2027届",),
    )


def _truncated_result(*titles: str) -> AdapterResult:
    return AdapterResult(
        complete=False,
        opportunities=tuple(_candidate(title) for title in titles),
        category_labels=("研发",),
        city_labels=("杭州",),
        cohort_labels=("2027届",),
        truncated=True,
    )


def test_adapter_accepts_same_list_url_for_distinct_job_titles() -> None:
    source = _source()

    validated = validate_adapter_result(
        _result("后端开发工程师", "前端开发工程师"),
        source=source,
        allowed_hosts=frozenset({"jobs.example.com"}),
    )

    assert [item.title for item in validated.opportunities] == [
        "后端开发工程师",
        "前端开发工程师",
    ]


def test_adapter_rejects_duplicate_normalized_job_identity() -> None:
    source = _source()

    with pytest.raises(CollectionRejected) as duplicate:
        validate_adapter_result(
            _result("平台 开发工程师", "  平台   开发工程师  "),
            source=source,
            allowed_hosts=frozenset({"jobs.example.com"}),
        )

    assert duplicate.value.error_code == "opportunities.adapter_duplicate_identity.v1"


def test_collection_creates_and_idempotently_updates_distinct_jobs_on_one_url() -> None:
    source = _source()
    result = _result("后端开发工程师", "前端开发工程师")

    first = apply_adapter_result(
        source_id=source.id,
        result=result,
        observed_at=OBSERVED_AT,
    )
    second = apply_adapter_result(
        source_id=source.id,
        result=result,
        observed_at=OBSERVED_AT,
    )

    assert first.created == 2
    assert second.created == 0
    assert second.changed == 0
    assert Opportunity.objects.filter(source=source).count() == 2
    assert (
        Opportunity.objects.filter(source=source)
        .values_list("identity_key", flat=True)
        .distinct()
        .count()
        == 2
    )


def test_collection_identity_survives_public_title_override() -> None:
    source = _source()
    result = _result("后端开发工程师")
    apply_adapter_result(
        source_id=source.id,
        result=result,
        observed_at=OBSERVED_AT,
    )
    opportunity = Opportunity.objects.get(source=source)
    identity_title = opportunity.normalized_identity_title
    Opportunity.objects.filter(pk=opportunity.id).update(
        title="后端平台工程师（人工展示名）",
        title_overridden=True,
    )

    repeated = apply_adapter_result(
        source_id=source.id,
        result=result,
        observed_at=OBSERVED_AT,
    )

    opportunity.refresh_from_db()
    assert repeated.created == 0
    assert Opportunity.objects.filter(source=source).count() == 1
    assert opportunity.title == "后端平台工程师（人工展示名）"
    assert opportunity.normalized_identity_title == identity_title


def test_truncated_collection_applies_seen_jobs_without_marking_unseen_data_missing() -> (
    None
):
    source = _source()
    apply_adapter_result(
        source_id=source.id,
        result=_result("既有岗位"),
        observed_at=OBSERVED_AT,
    )
    existing = Opportunity.objects.get(source=source)

    applied = apply_adapter_result(
        source_id=source.id,
        result=_truncated_result("新采集岗位"),
        observed_at=OBSERVED_AT + timedelta(hours=1),
    )

    existing.refresh_from_db()
    source.refresh_from_db()
    assert applied == CollectionApplyResult(
        created=1,
        changed=0,
        missing=0,
        skipped=0,
    )
    assert existing.list_missing is False
    assert existing.list_missing_count == 0
    assert source.filter_options_stale is True
    assert OpportunitySourceFilterOption.objects.filter(
        source=source,
        option__kind=OpportunityFilterKind.CITY,
        option__normalized_label="杭州",
        active=True,
    ).exists()


def test_collection_snapshot_keeps_distinct_jobs_on_one_url() -> None:
    source = _source()
    result = validate_adapter_result(
        _result("后端开发工程师", "前端开发工程师"),
        source=source,
        allowed_hosts=frozenset({"jobs.example.com"}),
    )
    source_check = OpportunityCheck.objects.create(
        source=source,
        target_kind=OpportunityCheck.TargetKind.SOURCE,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        state=OpportunityCheck.State.SUCCEEDED,
        http_status=200,
        started_at=OBSERVED_AT,
        completed_at=OBSERVED_AT,
        expires_at=OBSERVED_AT + timedelta(days=90),
    )

    snapshot = record_collection_snapshot(
        source=source,
        source_check=source_check,
        result=result,
        applied=CollectionApplyResult(created=2, changed=0, missing=0, skipped=0),
        observed_at=OBSERVED_AT,
    )

    assert len(snapshot.opportunity_identity_hashes) == 2
    assert len(snapshot.opportunity_field_hashes) == 2
    assert snapshot.difference_summary["pages_read"] == result.pages_read
    assert snapshot.difference_summary["observed_opportunities"] == 2
    assert snapshot.difference_summary["complete"] is True
    assert snapshot.difference_summary["truncated"] is False


def test_authoritative_listing_refreshes_present_jobs_without_detail_requests() -> None:
    source = _source()
    apply_adapter_result(
        source_id=source.id,
        result=_result("后端开发工程师"),
        observed_at=OBSERVED_AT,
    )
    opportunity = Opportunity.objects.get(source=source)
    Opportunity.objects.filter(pk=opportunity.id).update(
        verification_status=Opportunity.VerificationStatus.EXPIRED,
        consecutive_failures=2,
        last_error_code="opportunities.request_not_found.v1",
    )
    source_check = OpportunityCheck.objects.create(
        source=source,
        target_kind=OpportunityCheck.TargetKind.FILTERS,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        state=OpportunityCheck.State.SUCCEEDED,
        started_at=OBSERVED_AT,
        completed_at=OBSERVED_AT,
        expires_at=OBSERVED_AT + timedelta(days=90),
    )

    _listing_opportunity_success(
        source.id,
        checked_at=OBSERVED_AT + timedelta(hours=1),
        source_check=source_check,
    )

    opportunity.refresh_from_db()
    assert opportunity.verification_status == Opportunity.VerificationStatus.PENDING
    assert opportunity.consecutive_failures == 0
    assert opportunity.last_error_code == ""
    assert opportunity.last_success_at == OBSERVED_AT + timedelta(hours=1)
