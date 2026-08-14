from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.ids import new_ulid, normalize_ulid
from apps.operations.public import record_audit_entry

from ..defaults import project_default_filters
from ..models import (
    Opportunity,
    OpportunityDefaultFilterSelection,
    OpportunityFilterAssignment,
    OpportunityFilterKind,
    OpportunityFilterOption,
    OpportunityReviewItem,
    OpportunitySettings,
    OpportunitySource,
    OpportunitySourceHost,
)
from ..validators import (
    normalize_adapter_key,
    normalize_hostname,
    normalize_opportunity_url,
    normalized_text,
)
from .common import OpportunityCommandError, require_administrator, uuid_value
from .sources import source_audit_snapshot

_REVIEW_DECISIONS = frozenset({"ACCEPTED", "KEPT_MANUAL", "RESOLVED"})
_DEFAULT_FILTER_SELECTION_LIMIT = 200


@dataclass(frozen=True, slots=True)
class OpportunityAdministrationDraft:
    title: str
    target_url: str
    recruitment_type: str
    plan: str
    location_text: str
    public_evidence: str
    category_ids: tuple[UUID | str, ...]
    city_ids: tuple[UUID | str, ...]
    cohort_ids: tuple[UUID | str, ...]
    verification_status: str
    publication_state: str


@dataclass(frozen=True, slots=True)
class ReviewBatchResult:
    resolved_count: int
    confirmed_opportunity_count: int


def _review_confirms_opportunity(kind: str, decision: str) -> bool:
    return kind == OpportunityReviewItem.Kind.NEW and decision == "ACCEPTED"


def _ids(values, *, kind, source_id):
    if not isinstance(values, (list, tuple)) or not values:
        raise OpportunityCommandError(
            "opportunities.filters_required.v1", "请至少选择一个筛选项。"
        )
    identities = tuple(
        uuid_value(
            value, code="opportunities.filter_not_found.v1", message="筛选项不存在。"
        )
        for value in values
    )
    found = set(
        OpportunityFilterOption.objects.filter(
            id__in=identities,
            kind=kind,
            source_observations__active=True,
            source_observations__source_id=source_id,
        ).values_list("id", flat=True)
    )
    if found != set(identities):
        raise OpportunityCommandError(
            "opportunities.filter_not_found.v1", "筛选项不存在或已停用。"
        )
    return identities


def update_source(*, actor_id, source_id, draft, trace_code, client_ip):
    actor = require_administrator(actor_id)
    identity = uuid_value(
        source_id, code="opportunities.source_not_found.v1", message="招聘来源不存在。"
    )
    try:
        company = normalized_text(draft.company_name, maximum=120, field="企业名称")
        url, hostname = normalize_opportunity_url(draft.official_url)
        note = (
            normalized_text(draft.note, maximum=500, field="来源备注")
            if draft.note
            else ""
        )
        adapter_key = normalize_adapter_key(draft.adapter_key)
        allowed_hosts = {
            normalize_hostname(value) for value in (draft.allowed_hosts or (hostname,))
        }
    except ValidationError as error:
        raise OpportunityCommandError(
            "opportunities.source_invalid.v1", str(error.message)
        ) from None
    if hostname not in allowed_hosts:
        raise OpportunityCommandError(
            "opportunities.source_host_required.v1",
            "允许域名必须包含官方入口域名。",
        )
    if not isinstance(draft.respect_robots_txt, bool):
        raise OpportunityCommandError(
            "opportunities.source_robots_invalid.v1", "robots.txt 设置不合法。"
        )
    try:
        request_interval = int(draft.request_interval_seconds)
        max_pages = int(draft.max_pages)
        max_items = int(draft.max_opportunities)
        max_duration = int(draft.max_duration_seconds)
    except (TypeError, ValueError):
        raise OpportunityCommandError(
            "opportunities.source_limit_invalid.v1", "采集限制不合法。"
        ) from None
    if not (
        2 <= request_interval <= 3600
        and 1 <= max_pages <= 100
        and 1 <= max_items <= 5000
        and 1 <= max_duration <= 600
    ):
        raise OpportunityCommandError(
            "opportunities.source_limit_invalid.v1", "采集限制不合法。"
        )
    with transaction.atomic():
        try:
            row = OpportunitySource.objects.select_for_update().get(pk=identity)
        except OpportunitySource.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.source_not_found.v1", "招聘来源不存在。"
            ) from None
        before = source_audit_snapshot(row)
        row.company_name = company
        row.normalized_company_name = company.casefold()
        if draft.source_type not in OpportunitySource.SourceType.values:
            raise OpportunityCommandError(
                "opportunities.choice_invalid.v1", "来源类型不合法。"
            )
        row.source_type = draft.source_type
        row.official_url = url
        row.note = note
        row.adapter_key = adapter_key
        row.respect_robots_txt = draft.respect_robots_txt
        row.request_interval_seconds = request_interval
        row.max_pages = max_pages
        row.max_opportunities = max_items
        row.max_duration_seconds = max_duration
        row.row_version = F("row_version") + 1
        row.save(
            update_fields=(
                "company_name",
                "normalized_company_name",
                "source_type",
                "official_url",
                "note",
                "adapter_key",
                "respect_robots_txt",
                "request_interval_seconds",
                "max_pages",
                "max_opportunities",
                "max_duration_seconds",
                "row_version",
                "updated_at",
            )
        )
        row.refresh_from_db()
        OpportunitySourceHost.objects.filter(source=row).exclude(
            hostname__in=allowed_hosts
        ).delete()
        OpportunitySourceHost.objects.bulk_create(
            [
                OpportunitySourceHost(source=row, hostname=value)
                for value in sorted(allowed_hosts)
            ],
            ignore_conflicts=True,
        )
        record_audit_entry(
            action="opportunities.source.update",
            actor_id=actor,
            target_id=str(row.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=source_audit_snapshot(row),
            summary="Update opportunity source",
        )
    return row


def disable_source(*, actor_id, source_id, trace_code, client_ip):
    actor = require_administrator(actor_id)
    identity = uuid_value(
        source_id, code="opportunities.source_not_found.v1", message="招聘来源不存在。"
    )
    with transaction.atomic():
        row = OpportunitySource.objects.select_for_update().get(pk=identity)
        before = row.enabled
        if before:
            Opportunity.objects.select_for_update().filter(
                source=row, publication_state=Opportunity.PublicationState.PUBLISHED
            ).update(
                source_disabled_previous_state=Opportunity.PublicationState.PUBLISHED,
                publication_state=Opportunity.PublicationState.WITHDRAWN,
                updated_at=timezone.now(),
            )
            row.publicly_visible = False
            row.enabled = False
            row.row_version = F("row_version") + 1
            row.save(
                update_fields=(
                    "enabled",
                    "publicly_visible",
                    "row_version",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="opportunities.source.deactivate",
                actor_id=actor,
                target_id=str(row.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={"enabled": before},
                after={"enabled": False},
                summary="Disable opportunity source",
            )
        row.refresh_from_db()
    return row


def update_opportunity(*, actor_id, opportunity_id, draft, trace_code, client_ip):
    actor = require_administrator(actor_id)
    identity = uuid_value(
        opportunity_id,
        code="opportunities.opportunity_not_found.v1",
        message="岗位不存在。",
    )
    with transaction.atomic():
        row = Opportunity.objects.select_for_update().get(pk=identity)
        source_id = row.source_id
        try:
            title = normalized_text(draft.title, maximum=200, field="岗位标题")
            target_url, host = normalize_opportunity_url(draft.target_url)
            plan = normalized_text(draft.plan, maximum=200, field="招聘计划")
            location = normalized_text(
                draft.location_text, maximum=300, field="工作地点"
            )
            evidence = normalized_text(
                draft.public_evidence, maximum=1200, field="公开证据"
            )
        except ValidationError as error:
            raise OpportunityCommandError(
                "opportunities.opportunity_invalid.v1", str(error.message)
            ) from None
        if host not in set(row.source.allowed_hosts.values_list("hostname", flat=True)):
            raise OpportunityCommandError(
                "opportunities.url_host_not_allowed.v1", "岗位地址不在来源允许域名内。"
            )
        category_ids = _ids(
            draft.category_ids, kind=OpportunityFilterKind.CATEGORY, source_id=source_id
        )
        city_ids = _ids(
            draft.city_ids, kind=OpportunityFilterKind.CITY, source_id=source_id
        )
        cohort_ids = _ids(
            draft.cohort_ids, kind=OpportunityFilterKind.COHORT, source_id=source_id
        )
        if draft.recruitment_type not in Opportunity.RecruitmentType.values:
            raise OpportunityCommandError(
                "opportunities.choice_invalid.v1", "招聘类型不合法。"
            )
        if draft.verification_status not in Opportunity.VerificationStatus.values:
            raise OpportunityCommandError(
                "opportunities.choice_invalid.v1", "核实状态不合法。"
            )
        if draft.publication_state not in Opportunity.PublicationState.values:
            raise OpportunityCommandError(
                "opportunities.choice_invalid.v1", "上下架状态不合法。"
            )
        (
            row.title,
            row.target_url,
            row.recruitment_type,
            row.plan,
            row.location_text,
            row.public_evidence,
        ) = (
            title,
            target_url,
            draft.recruitment_type,
            plan,
            location,
            evidence,
        )
        row.verification_status = draft.verification_status
        row.publication_state = draft.publication_state
        row.title_overridden = row.target_url_overridden = (
            row.recruitment_type_overridden
        ) = row.plan_overridden = row.location_overridden = (
            row.public_evidence_overridden
        ) = row.category_overridden = row.city_overridden = row.cohort_overridden = True
        row.row_version = F("row_version") + 1
        row.save(
            update_fields=(
                "title",
                "target_url",
                "recruitment_type",
                "plan",
                "location_text",
                "public_evidence",
                "verification_status",
                "publication_state",
                "title_overridden",
                "target_url_overridden",
                "recruitment_type_overridden",
                "plan_overridden",
                "location_overridden",
                "public_evidence_overridden",
                "category_overridden",
                "city_overridden",
                "cohort_overridden",
                "row_version",
                "updated_at",
            )
        )
        OpportunityFilterAssignment.objects.filter(
            opportunity=row, origin=OpportunityFilterAssignment.Origin.MANUAL
        ).delete()
        OpportunityFilterAssignment.objects.bulk_create(
            [
                OpportunityFilterAssignment(
                    opportunity=row,
                    option_id=option_id,
                    origin=OpportunityFilterAssignment.Origin.MANUAL,
                )
                for option_id in (*category_ids, *city_ids, *cohort_ids)
            ]
        )
        record_audit_entry(
            action="opportunities.opportunity.update",
            actor_id=actor,
            target_id=str(row.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={},
            after={
                "verification_status": row.verification_status,
                "publication_state": row.publication_state,
            },
            summary="Update opportunity",
        )
        row.refresh_from_db()
    return row


def resolve_review_item(*, actor_id, review_id, decision, trace_code, client_ip):
    actor = require_administrator(actor_id)
    if decision not in _REVIEW_DECISIONS:
        raise OpportunityCommandError(
            "opportunities.review_decision_invalid.v1", "审核决定不合法。"
        )
    with transaction.atomic():
        try:
            row = (
                OpportunityReviewItem.objects.select_for_update()
                .select_related("opportunity")
                .get(pk=str(review_id), state=OpportunityReviewItem.State.OPEN)
            )
        except OpportunityReviewItem.DoesNotExist:
            raise OpportunityCommandError(
                "opportunities.review_not_found.v1", "审核项不存在或已处理。"
            ) from None
        row.state = decision
        row.reviewed_by_id = actor
        row.reviewed_at = timezone.now()
        row.save(update_fields=("state", "reviewed_by", "reviewed_at", "updated_at"))
        if _review_confirms_opportunity(row.kind, decision):
            row.opportunity.verification_status = (
                Opportunity.VerificationStatus.CONFIRMED
            )
            row.opportunity.row_version = F("row_version") + 1
            row.opportunity.save(
                update_fields=("verification_status", "row_version", "updated_at")
            )
        record_audit_entry(
            action="opportunities.review.resolve",
            actor_id=actor,
            target_id=str(row.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"state": "OPEN"},
            after={"state": decision},
            summary="Resolve opportunity review",
        )
    return row


def resolve_review_items(
    *, actor_id, review_ids, decision, trace_code, client_ip
) -> ReviewBatchResult:
    actor = require_administrator(actor_id)
    if decision not in _REVIEW_DECISIONS:
        raise OpportunityCommandError(
            "opportunities.review_decision_invalid.v1", "审核决定不合法。"
        )
    scope = "ALL" if review_ids is None else "PAGE"
    identities = None
    if review_ids is not None:
        if not isinstance(review_ids, (list, tuple)) or not 1 <= len(review_ids) <= 50:
            raise OpportunityCommandError(
                "opportunities.review_batch_invalid.v1",
                "当前页批量审核请求不合法。",
            )
        try:
            identities = tuple(
                dict.fromkeys(normalize_ulid(value) for value in review_ids)
            )
        except (TypeError, ValueError):
            raise OpportunityCommandError(
                "opportunities.review_batch_invalid.v1",
                "当前页批量审核请求不合法。",
            ) from None

    with transaction.atomic():
        rows = OpportunityReviewItem.objects.select_for_update().filter(
            state=OpportunityReviewItem.State.OPEN
        )
        if identities is not None:
            rows = rows.filter(pk__in=identities)
        locked = tuple(
            rows.order_by("created_at", "id").values_list(
                "id", "opportunity_id", "kind"
            )
        )
        if not locked:
            return ReviewBatchResult(0, 0)

        reviewed_at = timezone.now()
        locked_ids = tuple(row_id for row_id, _opportunity_id, _kind in locked)
        resolved_count = OpportunityReviewItem.objects.filter(
            pk__in=locked_ids,
            state=OpportunityReviewItem.State.OPEN,
        ).update(
            state=decision,
            reviewed_by_id=actor,
            reviewed_at=reviewed_at,
            updated_at=reviewed_at,
        )
        confirmed_ids = tuple(
            opportunity_id
            for _row_id, opportunity_id, kind in locked
            if _review_confirms_opportunity(kind, decision)
        )
        confirmed_count = 0
        if confirmed_ids:
            confirmed_count = Opportunity.objects.filter(pk__in=confirmed_ids).update(
                verification_status=Opportunity.VerificationStatus.CONFIRMED,
                row_version=F("row_version") + 1,
                updated_at=reviewed_at,
            )
        record_audit_entry(
            action="opportunities.review.resolve_batch",
            actor_id=actor,
            target_id=new_ulid(),
            trace_code=trace_code,
            client_ip=client_ip,
            before={},
            after={
                "count": resolved_count,
                "scope": scope,
                "state": decision,
            },
            summary="Resolve opportunity review batch",
        )
    return ReviewBatchResult(resolved_count, confirmed_count)


def _bounded_default_values(values, *, label):
    if not isinstance(values, (list, tuple)):
        raise OpportunityCommandError(
            "opportunities.default_filters_invalid.v1",
            f"默认{label}配置不合法。",
        )
    deduplicated = tuple(dict.fromkeys(values))
    if len(deduplicated) > _DEFAULT_FILTER_SELECTION_LIMIT:
        raise OpportunityCommandError(
            "opportunities.default_filters_invalid.v1",
            f"默认{label}最多选择 {_DEFAULT_FILTER_SELECTION_LIMIT} 项。",
        )
    return deduplicated


def _default_option_ids(values, *, kind, label):
    raw_values = _bounded_default_values(values, label=label)
    identities = tuple(
        uuid_value(
            value,
            code="opportunities.filter_not_found.v1",
            message=f"默认{label}不存在。",
        )
        for value in raw_values
    )
    found = set(
        OpportunityFilterOption.objects.filter(
            id__in=identities,
            kind=kind,
            source_observations__active=True,
            source_observations__source__enabled=True,
            source_observations__source__publicly_visible=True,
        )
        .distinct()
        .values_list("id", flat=True)
    )
    if found != set(identities):
        raise OpportunityCommandError(
            "opportunities.filter_not_found.v1",
            f"默认{label}不存在或不在公开筛选范围内。",
        )
    return identities


def _default_source_ids(values):
    raw_values = _bounded_default_values(values, label="企业")
    identities = tuple(
        uuid_value(
            value,
            code="opportunities.source_not_found.v1",
            message="默认企业不存在。",
        )
        for value in raw_values
    )
    found = set(
        OpportunitySource.objects.filter(
            id__in=identities,
            enabled=True,
            publicly_visible=True,
        ).values_list("id", flat=True)
    )
    if found != set(identities):
        raise OpportunityCommandError(
            "opportunities.source_not_found.v1",
            "默认企业不存在或已停止公开。",
        )
    return identities


def _default_choice_values(values, *, allowed, label):
    selected = _bounded_default_values(values, label=label)
    if any(not isinstance(value, str) or value not in allowed for value in selected):
        raise OpportunityCommandError(
            "opportunities.default_filters_invalid.v1",
            f"默认{label}配置不合法。",
        )
    return selected


def _default_filter_audit(values):
    return {
        "cities": [str(value) for value in values.city_ids],
        "statuses": list(values.verification_statuses),
        "companies": [str(value) for value in values.source_ids],
        "recruitment_types": list(values.recruitment_types),
        "categories": [str(value) for value in values.category_ids],
        "cohorts": [str(value) for value in values.cohort_ids],
    }


def update_opportunity_settings(
    *,
    actor_id,
    city_ids=(),
    verification_statuses=(),
    source_ids=(),
    recruitment_types=(),
    category_ids=(),
    cohort_ids=(),
    trace_code,
    client_ip,
):
    actor = require_administrator(actor_id)
    city_ids = _default_option_ids(
        city_ids, kind=OpportunityFilterKind.CITY, label="城市"
    )
    verification_statuses = _default_choice_values(
        verification_statuses,
        allowed=Opportunity.VerificationStatus.values,
        label="核实状态",
    )
    source_ids = _default_source_ids(source_ids)
    recruitment_types = _default_choice_values(
        recruitment_types,
        allowed=Opportunity.RecruitmentType.values,
        label="招聘类型",
    )
    category_ids = _default_option_ids(
        category_ids, kind=OpportunityFilterKind.CATEGORY, label="岗位类别"
    )
    cohort_ids = _default_option_ids(
        cohort_ids, kind=OpportunityFilterKind.COHORT, label="届别"
    )

    with transaction.atomic():
        row, _ = OpportunitySettings.objects.select_for_update().get_or_create(pk=1)
        before_values = project_default_filters(
            row.default_filter_selections.all(), settings_exists=True
        )
        row.default_filter_selections.all().delete()
        selections = [
            *(
                OpportunityDefaultFilterSelection(
                    settings=row,
                    kind=OpportunityDefaultFilterSelection.Kind.CITY,
                    option_id=value,
                )
                for value in city_ids
            ),
            *(
                OpportunityDefaultFilterSelection(
                    settings=row,
                    kind=OpportunityDefaultFilterSelection.Kind.STATUS,
                    value=value,
                )
                for value in verification_statuses
            ),
            *(
                OpportunityDefaultFilterSelection(
                    settings=row,
                    kind=OpportunityDefaultFilterSelection.Kind.COMPANY,
                    source_id=value,
                )
                for value in source_ids
            ),
            *(
                OpportunityDefaultFilterSelection(
                    settings=row,
                    kind=OpportunityDefaultFilterSelection.Kind.RECRUITMENT_TYPE,
                    value=value,
                )
                for value in recruitment_types
            ),
            *(
                OpportunityDefaultFilterSelection(
                    settings=row,
                    kind=OpportunityDefaultFilterSelection.Kind.CATEGORY,
                    option_id=value,
                )
                for value in category_ids
            ),
            *(
                OpportunityDefaultFilterSelection(
                    settings=row,
                    kind=OpportunityDefaultFilterSelection.Kind.COHORT,
                    option_id=value,
                )
                for value in cohort_ids
            ),
        ]
        OpportunityDefaultFilterSelection.objects.bulk_create(selections)
        row.row_version = F("row_version") + 1
        row.save(update_fields=("row_version", "updated_at"))
        row.refresh_from_db()
        after_values = project_default_filters(selections, settings_exists=True)
        record_audit_entry(
            action="opportunities.settings.update",
            actor_id=actor,
            target_id="1",
            trace_code=trace_code,
            client_ip=client_ip,
            before=_default_filter_audit(before_values),
            after=_default_filter_audit(after_values),
            summary="Update opportunity settings",
        )
    return row


__all__ = [
    "OpportunityAdministrationDraft",
    "update_source",
    "disable_source",
    "update_opportunity",
    "resolve_review_item",
    "update_opportunity_settings",
]
