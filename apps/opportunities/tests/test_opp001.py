from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Account, RoleAssignment
from apps.core.observability.trace import new_trace_code
from apps.opportunities.models import (
    Opportunity,
    OpportunityFilterAssignment,
    OpportunityFilterKind,
    OpportunityReviewItem,
    OpportunitySource,
)
from apps.opportunities.public import (
    OpportunityCommandError,
    OpportunityDraft,
    SourceDraft,
    activate_source,
    bookmarked_opportunities,
    create_opportunity,
    create_source,
    mark_source_initial_success,
    public_opportunities,
    public_opportunity_sources,
    replace_source_filter_options,
    set_opportunity_bookmark,
    withdraw_opportunity,
)

pytestmark = pytest.mark.django_db


def _account(*, administrator: bool = False) -> Account:
    account = Account.objects.create_account(
        email=f"opp-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(account=account, role="AUTHOR")
    if administrator:
        RoleAssignment.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _source(admin: Account):
    return create_source(
        actor_id=admin.id,
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


def _ready_source(admin: Account):
    source = _source(admin)
    activate_source(
        actor_id=admin.id,
        source_id=source.source_id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    mark_source_initial_success(
        source_id=source.source_id,
        checked_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
    )
    options = {}
    for kind, values in (
        (OpportunityFilterKind.CITY, ("杭州",)),
        (OpportunityFilterKind.CATEGORY, ("研发",)),
        (OpportunityFilterKind.COHORT, ("2027届",)),
    ):
        options[kind] = replace_source_filter_options(
            source_id=source.source_id,
            kind=kind,
            values=values,
            observed_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        )[0]
    return source, options


def _opportunity(admin: Account):
    source, options = _ready_source(admin)
    result = create_opportunity(
        actor_id=admin.id,
        draft=OpportunityDraft(
            source_id=source.source_id,
            title="后端开发工程师",
            target_url="https://jobs.example.com/campus/123",
            recruitment_type="CAMPUS",
            plan="2027 届校园招聘",
            location_text="杭州",
            public_evidence="来自示例科技校园招聘公开列表。",
            category_ids=(options[OpportunityFilterKind.CATEGORY].option_id,),
            city_ids=(options[OpportunityFilterKind.CITY].option_id,),
            cohort_ids=(options[OpportunityFilterKind.COHORT].option_id,),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    return source, result


def test_only_administrator_can_create_source_and_defaults_are_safe() -> None:
    author = _account()
    with pytest.raises(OpportunityCommandError) as denied:
        _source(author)
    assert denied.value.code == "opportunities.admin_required.v1"

    admin = _account(administrator=True)
    result = _source(admin)
    source = OpportunitySource.objects.get(pk=result.source_id)
    assert source.enabled is False
    assert source.publicly_visible is False
    assert source.respect_robots_txt is True
    assert source.request_interval_seconds == 2
    assert list(source.allowed_hosts.values_list("hostname", flat=True)) == [
        "jobs.example.com"
    ]
    with pytest.raises(OpportunityCommandError) as duplicate:
        _source(admin)
    assert duplicate.value.code == "opportunities.source_conflict.v1"


def test_manual_opportunity_is_pending_public_and_enters_review_queue() -> None:
    admin = _account(administrator=True)
    _, result = _opportunity(admin)

    opportunity = Opportunity.objects.get(pk=result.opportunity_id)
    assert opportunity.verification_status == Opportunity.VerificationStatus.PENDING
    assert opportunity.publication_state == Opportunity.PublicationState.PUBLISHED
    assert OpportunityReviewItem.objects.filter(
        opportunity=opportunity,
        kind=OpportunityReviewItem.Kind.NEW,
        state=OpportunityReviewItem.State.OPEN,
    ).exists()
    page = public_opportunities()
    assert [item.opportunity_id for item in page.items] == [opportunity.id]
    assert page.items[0].company_name == "示例科技"
    assert page.items[0].categories == ("研发",)


def test_public_query_hides_withdrawn_but_owner_bookmarks_keep_history() -> None:
    admin = _account(administrator=True)
    reader = _account()
    other_reader = _account()
    _, result = _opportunity(admin)

    set_opportunity_bookmark(
        account_id=reader.id,
        opportunity_id=result.opportunity_id,
        selected=True,
    )
    withdraw_opportunity(
        actor_id=admin.id,
        opportunity_id=result.opportunity_id,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )

    assert public_opportunities().items == ()
    saved = bookmarked_opportunities(account_id=reader.id)
    assert [item.opportunity_id for item in saved.items] == [result.opportunity_id]
    assert saved.items[0].availability_label == "已下架"
    assert bookmarked_opportunities(account_id=other_reader.id).items == ()


def test_public_query_hides_a_position_missing_from_two_complete_listings() -> None:
    admin = _account(administrator=True)
    _, result = _opportunity(admin)
    Opportunity.objects.filter(pk=result.opportunity_id).update(
        list_missing=True,
        list_missing_count=2,
    )

    assert public_opportunities().items == ()


def test_public_source_count_excludes_positions_missing_from_two_listings() -> None:
    admin = _account(administrator=True)
    source, result = _opportunity(admin)
    Opportunity.objects.filter(pk=result.opportunity_id).update(
        list_missing=True,
        list_missing_count=2,
    )

    page = public_opportunity_sources()

    assert len(page.items) == 1
    assert page.items[0].public_opportunity_count == 0


def test_database_rejects_invalid_enums_and_public_disabled_source() -> None:
    admin = _account(administrator=True)
    source, result = _opportunity(admin)

    with pytest.raises(IntegrityError), transaction.atomic():
        Opportunity.objects.filter(pk=result.opportunity_id).update(
            verification_status="UNKNOWN"
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        OpportunitySource.objects.filter(pk=source.source_id).update(enabled=False)


def test_opportunity_url_is_normalized_and_must_use_source_allowlist() -> None:
    admin = _account(administrator=True)
    source, options = _ready_source(admin)
    draft_fields = {
        "source_id": source.source_id,
        "title": "平台开发工程师",
        "recruitment_type": "CAMPUS",
        "plan": "2027 届校园招聘",
        "location_text": "杭州",
        "public_evidence": "来自企业公开招聘列表。",
        "category_ids": (options[OpportunityFilterKind.CATEGORY].option_id,),
        "city_ids": (options[OpportunityFilterKind.CITY].option_id,),
        "cohort_ids": (options[OpportunityFilterKind.COHORT].option_id,),
    }

    with pytest.raises(OpportunityCommandError) as denied:
        create_opportunity(
            actor_id=admin.id,
            draft=OpportunityDraft(
                target_url="https://other.example.com/campus/123",
                **draft_fields,
            ),
            trace_code=new_trace_code(),
            client_ip="127.0.0.1",
        )
    assert denied.value.code == "opportunities.url_host_not_allowed.v1"

    result = create_opportunity(
        actor_id=admin.id,
        draft=OpportunityDraft(
            target_url=(
                "HTTPS://jobs.example.com:443/campus/archive/../123"
                "?utm_source=test&ref=official#apply"
            ),
            **draft_fields,
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    row = Opportunity.objects.get(pk=result.opportunity_id)
    assert row.target_url == "https://jobs.example.com/campus/123?ref=official#apply"
    assert row.normalized_target_url == row.target_url


def test_manual_values_remain_the_public_projection_when_collected_values_exist() -> (
    None
):
    admin = _account(administrator=True)
    source, result = _opportunity(admin)
    collected = replace_source_filter_options(
        source_id=source.source_id,
        kind=OpportunityFilterKind.CATEGORY,
        values=("研发", "平台工程"),
        observed_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
    )[1]
    row = Opportunity.objects.get(pk=result.opportunity_id)
    OpportunityFilterAssignment.objects.create(
        opportunity=row,
        option_id=collected.option_id,
        origin=OpportunityFilterAssignment.Origin.COLLECTED,
    )

    row.refresh_from_db()
    assert row.title_overridden is True
    assert row.target_url_overridden is True
    assert row.recruitment_type_overridden is True
    assert row.plan_overridden is True
    assert row.location_overridden is True
    assert row.public_evidence_overridden is True
    assert row.category_overridden is True
    assert row.city_overridden is True
    assert row.cohort_overridden is True
    assert public_opportunities().items[0].categories == ("研发",)


def test_hidden_opportunity_cannot_be_newly_bookmarked_or_read() -> None:
    admin = _account(administrator=True)
    reader = _account()
    source = _source(admin)
    hidden = Opportunity.objects.create(
        source_id=source.source_id,
        title="未公开岗位",
        target_url="https://jobs.example.com/private/123",
        normalized_target_url="https://jobs.example.com/private/123",
        normalized_identity_title="未公开岗位",
        identity_key="f" * 64,
        recruitment_type=Opportunity.RecruitmentType.CAMPUS,
        plan="内部采集结果",
        location_text="杭州",
        public_evidence="尚未形成公开基线。",
        verification_status=Opportunity.VerificationStatus.PENDING,
        publication_state=Opportunity.PublicationState.PUBLISHED,
        origin=Opportunity.Origin.CRAWLER,
    )

    with pytest.raises(OpportunityCommandError) as denied:
        set_opportunity_bookmark(
            account_id=reader.id,
            opportunity_id=hidden.id,
            selected=True,
        )

    assert denied.value.code == "opportunities.opportunity_not_public.v1"
    assert bookmarked_opportunities(account_id=reader.id).items == ()
