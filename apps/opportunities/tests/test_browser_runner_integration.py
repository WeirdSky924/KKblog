from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.accounts.models import Account, RoleAssignment
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.opportunities.checks.adapters import (
    AdapterResult,
    CollectedOpportunity,
    register_adapter,
)
from apps.opportunities.checks.http import DomainRateLimiter
from apps.opportunities.models import Opportunity, OpportunityCheck, OpportunitySource
from apps.opportunities.public import SourceDraft, create_source
from apps.opportunities.services.runner import run_source_check

pytestmark = pytest.mark.django_db


class BrowserAdapter:
    key = "browser-runner-test-v1"
    browser_required = True
    browser_collection_enabled = True
    authoritative_listing = True

    def collect(self, **kwargs):
        self.request = kwargs
        return AdapterResult(
            complete=True,
            opportunities=(
                CollectedOpportunity(
                    title="算法工程师",
                    target_url="https://jobs.example.com/campus/1",
                    recruitment_type="CAMPUS",
                    plan="2027届校园招聘",
                    location_text="杭州",
                    category_labels=("算法",),
                    city_labels=("杭州",),
                    cohort_labels=("2027届",),
                ),
            ),
            category_labels=("算法",),
            city_labels=("杭州",),
            cohort_labels=("2027届",),
        )


class TruncatedBrowserAdapter(BrowserAdapter):
    key = "browser-runner-truncated-test-v1"

    def collect(self, **kwargs):
        complete = super().collect(**kwargs)
        return AdapterResult(
            complete=False,
            opportunities=complete.opportunities,
            category_labels=complete.category_labels,
            city_labels=complete.city_labels,
            cohort_labels=complete.cohort_labels,
            truncated=True,
        )


def _source() -> OpportunitySource:
    account = Account.objects.create_account(
        email=f"browser-runner-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    created = create_source(
        actor_id=account.id,
        draft=SourceDraft(
            company_name="示例科技",
            source_type="CAMPUS",
            official_url="https://jobs.example.com/campus",
            note="浏览器采集测试",
            adapter_key="browser-runner-test-v1",
            max_duration_seconds=90,
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    OpportunitySource.objects.filter(pk=created.source_id).update(enabled=True)
    return OpportunitySource.objects.get(pk=created.source_id)


def test_browser_runner_skips_plain_http_probe_and_applies_collection() -> None:
    adapter = BrowserAdapter()
    register_adapter(adapter, replace=True)
    source = _source()

    def reject_plain_http(*args):
        del args
        raise AssertionError("browser collection must not use the plain HTTP probe")

    result = run_source_check(
        source_id=source.id,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        task_run_id="",
        heartbeat=lambda: None,
        rate_limiter=DomainRateLimiter(),
        client_factory=reject_plain_http,
        clock=FrozenClock(datetime(2026, 8, 14, 1, 0, tzinfo=UTC)),
        monotonic=lambda: 10.0,
    )

    assert result.state == "SUCCEEDED"
    assert result.created == 1
    assert Opportunity.objects.get(source=source).title == "算法工程师"
    assert adapter.request["config"]["_max_duration_seconds"] == 90
    assert adapter.request["initial_response"] is None


def test_browser_runner_applies_seen_jobs_without_publishing_truncated_source() -> None:
    adapter = TruncatedBrowserAdapter()
    register_adapter(adapter, replace=True)
    source = _source()
    source.adapter_key = adapter.key
    source.save(update_fields=("adapter_key", "updated_at"))

    result = run_source_check(
        source_id=source.id,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        task_run_id="",
        heartbeat=lambda: None,
        rate_limiter=DomainRateLimiter(),
        clock=FrozenClock(datetime(2026, 8, 14, 1, 0, tzinfo=UTC)),
        monotonic=lambda: 10.0,
    )

    source.refresh_from_db()
    assert result.state == "TRUNCATED"
    assert result.created == 1
    assert result.missing == 0
    assert Opportunity.objects.get(source=source).title == "算法工程师"
    assert source.publicly_visible is False
    assert source.last_error_code == "opportunities.collection_truncated.v1"


def test_truncated_source_keeps_confirmed_published_jobs_visible() -> None:
    complete_adapter = BrowserAdapter()
    register_adapter(complete_adapter, replace=True)
    source = _source()
    run_source_check(
        source_id=source.id,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        task_run_id="",
        heartbeat=lambda: None,
        rate_limiter=DomainRateLimiter(),
        clock=FrozenClock(datetime(2026, 8, 14, 1, 0, tzinfo=UTC)),
        monotonic=lambda: 10.0,
    )
    Opportunity.objects.filter(source=source).update(
        verification_status=Opportunity.VerificationStatus.CONFIRMED,
        publication_state=Opportunity.PublicationState.PUBLISHED,
    )
    truncated_adapter = TruncatedBrowserAdapter()
    register_adapter(truncated_adapter, replace=True)
    source.adapter_key = truncated_adapter.key
    source.publicly_visible = False
    source.save(update_fields=("adapter_key", "publicly_visible", "updated_at"))

    result = run_source_check(
        source_id=source.id,
        trigger=OpportunityCheck.Trigger.MANUAL_SOURCE,
        task_run_id="",
        heartbeat=lambda: None,
        rate_limiter=DomainRateLimiter(),
        clock=FrozenClock(datetime(2026, 8, 14, 2, 0, tzinfo=UTC)),
        monotonic=lambda: 10.0,
    )

    source.refresh_from_db()
    assert result.state == "TRUNCATED"
    assert source.publicly_visible is True
    assert source.check_state == OpportunitySource.CheckState.DEGRADED
    assert source.last_error_code == "opportunities.collection_truncated.v1"
