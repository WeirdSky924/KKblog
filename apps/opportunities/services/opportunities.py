from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F

from apps.operations.public import record_audit_entry

from ..models import (
    Opportunity,
    OpportunityFilterAssignment,
    OpportunityFilterKind,
    OpportunityFilterOption,
    OpportunityReviewItem,
    OpportunitySource,
)
from ..validators import (
    normalize_opportunity_identity_title,
    normalize_opportunity_url,
    normalized_text,
    opportunity_identity_key,
)
from .common import OpportunityCommandError, require_administrator, uuid_value


@dataclass(frozen=True, slots=True)
class OpportunityDraft:
    source_id: UUID | str
    title: str
    target_url: str
    recruitment_type: str
    plan: str
    location_text: str
    public_evidence: str
    category_ids: tuple[UUID | str, ...]
    city_ids: tuple[UUID | str, ...]
    cohort_ids: tuple[UUID | str, ...]


@dataclass(frozen=True, slots=True)
class OpportunityResult:
    opportunity_id: UUID
    verification_status: str
    publication_state: str
    row_version: int


def _choice(value: str, choices, *, field: str) -> str:
    if value not in {choice for choice, _ in choices}:
        raise OpportunityCommandError(
            "opportunities.choice_invalid.v1", f"{field}不合法。"
        )
    return value


def _option_ids(values, *, kind: str, field: str, source_id: UUID) -> tuple[UUID, ...]:
    if not isinstance(values, tuple | list) or not values:
        raise OpportunityCommandError(
            "opportunities.filters_required.v1", f"请至少选择一个{field}。"
        )
    identities = tuple(
        uuid_value(
            value,
            code="opportunities.filter_not_found.v1",
            message=f"{field}不存在。",
        )
        for value in values
    )
    if len(identities) != len(set(identities)):
        raise OpportunityCommandError(
            "opportunities.filter_duplicate.v1", f"{field}不能重复。"
        )
    found = {
        row.id
        for row in OpportunityFilterOption.objects.filter(
            id__in=identities,
            kind=kind,
            source_observations__active=True,
            source_observations__source_id=source_id,
        ).distinct()
    }
    if found != set(identities):
        raise OpportunityCommandError(
            "opportunities.filter_not_found.v1", f"{field}不存在或当前不可用。"
        )
    return identities


def _snapshot(row: Opportunity) -> dict[str, object]:
    return {
        "source_id": str(row.source_id),
        "title": row.title,
        "url_host": normalize_opportunity_url(row.target_url)[1],
        "recruitment_type": row.recruitment_type,
        "verification_status": row.verification_status,
        "publication_state": row.publication_state,
        "origin": row.origin,
        "row_version": row.row_version,
    }


def create_opportunity(
    *,
    actor_id,
    draft: OpportunityDraft,
    trace_code: str,
    client_ip: str,
) -> OpportunityResult:
    actor = require_administrator(actor_id)
    source_id = uuid_value(
        draft.source_id,
        code="opportunities.source_not_found.v1",
        message="招聘来源不存在。",
    )
    try:
        title = normalized_text(draft.title, maximum=200, field="岗位标题")
        identity_title = normalize_opportunity_identity_title(title)
        target_url, hostname = normalize_opportunity_url(draft.target_url)
        identity_key = opportunity_identity_key(target_url, identity_title)
        plan = normalized_text(draft.plan, maximum=200, field="招聘计划")
        location = normalized_text(draft.location_text, maximum=300, field="工作地点")
        evidence = normalized_text(
            draft.public_evidence,
            maximum=1200,
            field="公开证据",
        )
    except ValidationError as error:
        raise OpportunityCommandError(
            "opportunities.opportunity_invalid.v1", str(error.message)
        ) from None
    recruitment_type = _choice(
        draft.recruitment_type,
        Opportunity.RecruitmentType.choices,
        field="招聘类型",
    )
    category_ids = _option_ids(
        draft.category_ids,
        kind=OpportunityFilterKind.CATEGORY,
        field="岗位类别",
        source_id=source_id,
    )
    city_ids = _option_ids(
        draft.city_ids,
        kind=OpportunityFilterKind.CITY,
        field="城市",
        source_id=source_id,
    )
    cohort_ids = _option_ids(
        draft.cohort_ids,
        kind=OpportunityFilterKind.COHORT,
        field="届别",
        source_id=source_id,
    )
    try:
        with transaction.atomic():
            try:
                source = (
                    OpportunitySource.objects.select_for_update()
                    .prefetch_related("allowed_hosts")
                    .get(pk=source_id)
                )
            except OpportunitySource.DoesNotExist:
                raise OpportunityCommandError(
                    "opportunities.source_not_found.v1", "招聘来源不存在。"
                ) from None
            if not source.enabled or not source.publicly_visible:
                raise OpportunityCommandError(
                    "opportunities.source_not_public.v1",
                    "招聘来源首次完整检查成功后才能新增公开岗位。",
                )
            if hostname not in {item.hostname for item in source.allowed_hosts.all()}:
                raise OpportunityCommandError(
                    "opportunities.url_host_not_allowed.v1",
                    "岗位地址不在来源允许域名内。",
                )
            row = Opportunity.objects.create(
                source=source,
                title=title,
                target_url=target_url,
                normalized_target_url=target_url,
                normalized_identity_title=identity_title,
                identity_key=identity_key,
                recruitment_type=recruitment_type,
                plan=plan,
                location_text=location,
                public_evidence=evidence,
                verification_status=Opportunity.VerificationStatus.PENDING,
                publication_state=Opportunity.PublicationState.PUBLISHED,
                origin=Opportunity.Origin.MANUAL,
                title_overridden=True,
                target_url_overridden=True,
                recruitment_type_overridden=True,
                plan_overridden=True,
                location_overridden=True,
                public_evidence_overridden=True,
                category_overridden=True,
                city_overridden=True,
                cohort_overridden=True,
            )
            assignments = [
                OpportunityFilterAssignment(
                    opportunity=row,
                    option_id=option_id,
                    origin=OpportunityFilterAssignment.Origin.MANUAL,
                )
                for option_id in (*category_ids, *city_ids, *cohort_ids)
            ]
            OpportunityFilterAssignment.objects.bulk_create(assignments)
            OpportunityReviewItem.objects.create(
                opportunity=row,
                kind=OpportunityReviewItem.Kind.NEW,
                state=OpportunityReviewItem.State.OPEN,
                field_changes={"origin": "MANUAL"},
            )
            record_audit_entry(
                action="opportunities.opportunity.create",
                actor_id=actor,
                target_id=str(row.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after=_snapshot(row),
                summary="Create pending public opportunity",
            )
    except IntegrityError:
        raise OpportunityCommandError(
            "opportunities.opportunity_conflict.v1",
            "该来源下相同地址和标题的岗位已存在。",
        ) from None
    return OpportunityResult(
        row.id,
        row.verification_status,
        row.publication_state,
        row.row_version,
    )


def withdraw_opportunity(
    *, actor_id, opportunity_id, trace_code: str, client_ip: str
) -> OpportunityResult:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        opportunity_id,
        code="opportunities.opportunity_not_found.v1",
        message="岗位不存在。",
    )
    with transaction.atomic():
        try:
            row = Opportunity.objects.select_for_update().get(pk=identity)
        except Opportunity.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.opportunity_not_found.v1", "岗位不存在。"
            ) from None
        before = _snapshot(row)
        if row.publication_state != Opportunity.PublicationState.WITHDRAWN:
            row.publication_state = Opportunity.PublicationState.WITHDRAWN
            row.row_version = F("row_version") + 1
            row.save(update_fields=("publication_state", "row_version", "updated_at"))
            row.refresh_from_db(fields=("row_version", "updated_at"))
            record_audit_entry(
                action="opportunities.opportunity.withdraw",
                actor_id=actor,
                target_id=str(row.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before=before,
                after=_snapshot(row),
                summary="Withdraw public opportunity",
            )
    return OpportunityResult(
        row.id,
        row.verification_status,
        row.publication_state,
        row.row_version,
    )


__all__ = [
    "OpportunityDraft",
    "OpportunityResult",
    "create_opportunity",
    "withdraw_opportunity",
]
