from uuid import uuid4

import pytest
from django.utils import timezone

from apps.accounts.models import Account, RoleAssignment
from apps.core.observability.trace import new_trace_code
from apps.operations.public import TaskCancelled
from apps.opportunities.models import (
    OpportunityCheckRun,
    OpportunityCheckRunSource,
    OpportunitySource,
)
from apps.opportunities.public import request_check_cancellation, request_source_check
from apps.opportunities.queries.administration import admin_check_run_sources
from apps.opportunities.services.run_execution import execute_check_run

pytestmark = pytest.mark.django_db


def _administrator() -> Account:
    account = Account.objects.create_account(
        email=f"check-control-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _source() -> OpportunitySource:
    return OpportunitySource.objects.create(
        company_name="示例科技",
        normalized_company_name=f"示例科技-{uuid4()}",
        source_type=OpportunitySource.SourceType.CAMPUS,
        official_url=f"https://jobs-{uuid4()}.example.com/campus",
        adapter_key="example-v1",
        enabled=True,
        publicly_visible=True,
    )


def _request(admin: Account, source: OpportunitySource):
    return request_source_check(
        actor_id=admin.id,
        source_id=source.id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
        dispatcher=lambda run_id: None,
    )


def test_pending_source_check_cancels_immediately_and_cannot_execute() -> None:
    admin = _administrator()
    source = _source()
    requested = _request(admin, source)

    cancelled = request_check_cancellation(
        actor_id=admin.id,
        run_id=requested.run_id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )

    run = OpportunityCheckRun.objects.get(pk=requested.run_id)
    item = run.source_runs.get()
    assert cancelled.state == OpportunityCheckRun.State.CANCELLED
    assert run.state == OpportunityCheckRun.State.CANCELLED
    assert run.cancel_requested_at is not None
    assert run.completed_at is not None
    assert run.not_executed_sources == 1
    assert item.state == OpportunityCheckRunSource.State.NOT_EXECUTED
    assert item.completed_at is not None

    with pytest.raises(TaskCancelled):
        execute_check_run(run.id, lambda: None)

    history = admin_check_run_sources(actor_id=admin.id)
    assert history.items[0].state == OpportunityCheckRun.State.CANCELLED
    assert history.items[0].state_label == "已取消"
    assert history.items[0].can_cancel is False


def test_running_source_check_enters_visible_safe_cancellation_state() -> None:
    admin = _administrator()
    source = _source()
    requested = _request(admin, source)
    started_at = timezone.now()
    OpportunityCheckRun.objects.filter(pk=requested.run_id).update(
        state=OpportunityCheckRun.State.RUNNING,
        started_at=started_at,
    )
    OpportunityCheckRunSource.objects.filter(run_id=requested.run_id).update(
        state=OpportunityCheckRunSource.State.RUNNING,
        started_at=started_at,
    )

    cancelled = request_check_cancellation(
        actor_id=admin.id,
        run_id=requested.run_id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    repeated = request_check_cancellation(
        actor_id=admin.id,
        run_id=requested.run_id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )

    run = OpportunityCheckRun.objects.get(pk=requested.run_id)
    assert cancelled.state == OpportunityCheckRun.State.CANCEL_REQUESTED
    assert repeated.state == OpportunityCheckRun.State.CANCEL_REQUESTED
    assert run.cancel_requested_at is not None
    assert run.completed_at is None

    history = admin_check_run_sources(actor_id=admin.id)
    assert history.items[0].state == OpportunityCheckRun.State.CANCEL_REQUESTED
    assert history.items[0].state_label == "等待安全取消"
    assert history.items[0].can_cancel is False
