from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.accounts.models import Account, RoleAssignment
from apps.opportunities.models import (
    Opportunity,
    OpportunityCheck,
    OpportunityCheckRun,
    OpportunityCheckRunSource,
    OpportunityCollectionSnapshot,
    OpportunitySource,
)
from apps.opportunities.queries import administration

pytestmark = pytest.mark.django_db


def _administrator() -> Account:
    account = Account.objects.create_account(
        email=f"run-history-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _source() -> OpportunitySource:
    return OpportunitySource.objects.create(
        company_name="示例科技",
        normalized_company_name="示例科技",
        source_type=OpportunitySource.SourceType.CAMPUS,
        official_url=f"https://jobs-{uuid4()}.example.com/campus",
        adapter_key="example-v1",
        enabled=True,
        publicly_visible=True,
    )


def _opportunity(source, *, title: str, identity_key: str) -> Opportunity:
    target_url = f"{source.official_url}/jobs/{identity_key[:8]}"
    return Opportunity.objects.create(
        source=source,
        title=title,
        target_url=target_url,
        normalized_target_url=target_url,
        normalized_identity_title=title.casefold(),
        identity_key=identity_key,
        recruitment_type=Opportunity.RecruitmentType.CAMPUS,
        plan="2027 届校园招聘",
        location_text="杭州",
        public_evidence="官方招聘页面",
        origin=Opportunity.Origin.CRAWLER,
    )


def _snapshot(
    source,
    *,
    task_run_id: str,
    observed_at,
    identity_hashes,
    field_hashes,
) -> OpportunityCollectionSnapshot:
    check = OpportunityCheck.objects.create(
        source=source,
        task_run_id=task_run_id,
        target_kind=OpportunityCheck.TargetKind.FILTERS,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        state=OpportunityCheck.State.SUCCEEDED,
        started_at=observed_at,
        completed_at=observed_at,
        expires_at=observed_at + timedelta(days=90),
    )
    return OpportunityCollectionSnapshot.objects.create(
        source=source,
        source_check=check,
        complete=True,
        truncated=False,
        opportunity_identity_hashes=list(identity_hashes),
        opportunity_field_hashes=field_hashes,
        observed_at=observed_at,
        expires_at=observed_at + timedelta(days=90),
    )


def test_admin_run_history_is_paginated_by_source_and_exposes_job_changes() -> None:
    actor = _administrator()
    source = _source()
    now = timezone.now()
    created_key = "a" * 64
    changed_key = "b" * 64
    created = _opportunity(source, title="新岗位", identity_key=created_key)
    changed = _opportunity(source, title="更新岗位", identity_key=changed_key)
    _snapshot(
        source,
        task_run_id="PREVIOUS-RUN",
        observed_at=now - timedelta(hours=1),
        identity_hashes=(changed_key,),
        field_hashes={changed_key: "old-fields"},
    )
    run = OpportunityCheckRun.objects.create(
        kind=OpportunityCheckRun.Kind.SOURCE,
        trigger="MANUAL_SOURCE",
        state=OpportunityCheckRun.State.SUCCEEDED,
        task_run_id="CURRENT-RUN",
        total_sources=1,
        succeeded_sources=1,
        created_opportunities=1,
        changed_opportunities=1,
        started_at=now,
        completed_at=now,
    )
    source_run = OpportunityCheckRunSource.objects.create(
        run=run,
        source=source,
        position=1,
        state=OpportunityCheckRunSource.State.SUCCEEDED,
        created_opportunities=1,
        changed_opportunities=1,
        started_at=now,
        completed_at=now,
    )
    current_snapshot = _snapshot(
        source,
        task_run_id=run.task_run_id,
        observed_at=now,
        identity_hashes=(created_key, changed_key),
        field_hashes={created_key: "new-job", changed_key: "new-fields"},
    )

    page = administration.admin_check_run_sources(
        actor_id=actor.id,
        page=1,
        page_size=20,
    )
    detail = administration.admin_check_run_source_detail(
        actor_id=actor.id,
        source_run_id=source_run.id,
    )

    assert page.total == 1
    assert page.items[0].source_run_id == source_run.id
    assert page.items[0].company_name == source.company_name
    assert page.items[0].official_url == source.official_url
    assert detail is not None
    assert detail.snapshot_observed_at == current_snapshot.observed_at
    assert {(item.kind, item.opportunity_id) for item in detail.changes} == {
        ("CREATED", created.id),
        ("CHANGED", changed.id),
    }
