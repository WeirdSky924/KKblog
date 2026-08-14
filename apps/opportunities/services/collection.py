from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..checks.adapters import AdapterResult, CollectedOpportunity
from ..models import (
    Opportunity,
    OpportunityCollectionSnapshot,
    OpportunityFilterAssignment,
    OpportunityFilterKind,
    OpportunityFilterOption,
    OpportunityReviewItem,
    OpportunitySource,
)
from ..validators import (
    normalize_filter_label,
    normalize_opportunity_identity_title,
    normalize_opportunity_url,
    normalized_text,
    opportunity_identity_key,
)
from .sources import replace_source_filter_options


class CollectionRejected(ValueError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class CollectionApplyResult:
    created: int
    changed: int
    missing: int
    skipped: int


_COHORT_YEAR = re.compile(r"(?<!\d)((?:20)?\d{2})\s*届")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _labels(values, *, field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple | list):
        raise CollectionRejected("opportunities.adapter_result_invalid.v1")
    try:
        normalized = {
            normalized: display
            for display, normalized in (
                normalize_filter_label(value) for value in values
            )
        }
    except (TypeError, ValidationError):
        raise CollectionRejected("opportunities.adapter_result_invalid.v1") from None
    if len(normalized) > 100:
        raise CollectionRejected(f"opportunities.adapter_{field}_invalid.v1")
    return tuple(normalized[key] for key in sorted(normalized))


def _candidate(
    item: CollectedOpportunity,
    *,
    allowed_hosts: frozenset[str],
) -> CollectedOpportunity:
    if not isinstance(item, CollectedOpportunity):
        raise CollectionRejected("opportunities.adapter_result_invalid.v1")
    try:
        title = normalized_text(item.title, maximum=200, field="岗位标题")
        target_url, hostname = normalize_opportunity_url(item.target_url)
        plan = normalized_text(item.plan, maximum=200, field="招聘计划")
        location = normalized_text(item.location_text, maximum=300, field="工作地点")
    except ValidationError:
        raise CollectionRejected("opportunities.adapter_result_invalid.v1") from None
    if hostname not in allowed_hosts:
        raise CollectionRejected("opportunities.adapter_host_denied.v1")
    if item.recruitment_type not in Opportunity.RecruitmentType.values:
        raise CollectionRejected("opportunities.adapter_result_invalid.v1")
    return CollectedOpportunity(
        title=title,
        target_url=target_url,
        recruitment_type=item.recruitment_type,
        plan=plan,
        location_text=location,
        category_labels=_labels(item.category_labels, field="categories"),
        city_labels=_labels(item.city_labels, field="cities"),
        cohort_labels=_labels(item.cohort_labels, field="cohorts"),
    )


def _candidate_identity(item: CollectedOpportunity) -> tuple[str, str, str]:
    identity_title = normalize_opportunity_identity_title(item.title)
    return (
        item.target_url,
        identity_title,
        opportunity_identity_key(item.target_url, identity_title),
    )


def _target_cohort_years(observed_at) -> frozenset[int]:
    local_date = observed_at.astimezone(_SHANGHAI).date()
    current_cohort = local_date.year + int(local_date.month >= 7)
    return frozenset((current_cohort, current_cohort + 1))


def _filter_candidate_cohorts(
    item: CollectedOpportunity,
    *,
    target_years: frozenset[int],
) -> CollectedOpportunity | None:
    if not item.cohort_labels:
        return item
    observed_years = set()
    for label in item.cohort_labels:
        for match in _COHORT_YEAR.finditer(label):
            raw_year = match.group(1)
            year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
            if year in target_years:
                observed_years.add(year)
    if not observed_years:
        return None
    return CollectedOpportunity(
        title=item.title,
        target_url=item.target_url,
        recruitment_type=item.recruitment_type,
        plan=item.plan,
        location_text=item.location_text,
        category_labels=item.category_labels,
        city_labels=item.city_labels,
        cohort_labels=tuple(f"{year}届" for year in sorted(observed_years)),
    )


def validate_adapter_result(
    result: AdapterResult,
    *,
    source: OpportunitySource,
    allowed_hosts: frozenset[str],
    observed_at=None,
) -> AdapterResult:
    if (
        not isinstance(result, AdapterResult)
        or type(result.complete) is not bool
        or type(result.truncated) is not bool
        or isinstance(result.pages_read, bool)
        or not isinstance(result.pages_read, int)
        or not 1 <= result.pages_read <= source.max_pages
        or not isinstance(result.opportunities, tuple | list)
        or not isinstance(result.category_labels, tuple | list)
        or not isinstance(result.city_labels, tuple | list)
        or not isinstance(result.cohort_labels, tuple | list)
        or len(result.opportunities) > source.max_opportunities
        or (result.complete and result.truncated)
    ):
        raise CollectionRejected("opportunities.adapter_result_invalid.v1")
    _labels(result.category_labels, field="categories")
    _labels(result.city_labels, field="cities")
    _labels(result.cohort_labels, field="cohorts")
    normalized_candidates = tuple(
        _candidate(item, allowed_hosts=allowed_hosts) for item in result.opportunities
    )
    target_years = _target_cohort_years(observed_at or timezone.now())
    candidates = tuple(
        candidate
        for item in normalized_candidates
        if (candidate := _filter_candidate_cohorts(item, target_years=target_years))
        is not None
    )
    identities = [(_candidate_identity(item)[0:2]) for item in candidates]
    if len(identities) != len(set(identities)):
        raise CollectionRejected("opportunities.adapter_duplicate_identity.v1")
    return AdapterResult(
        complete=result.complete,
        opportunities=candidates,
        category_labels=_labels(
            [label for item in candidates for label in item.category_labels],
            field="categories",
        ),
        city_labels=_labels(
            [label for item in candidates for label in item.city_labels],
            field="cities",
        ),
        cohort_labels=_labels(
            [label for item in candidates for label in item.cohort_labels],
            field="cohorts",
        ),
        pages_read=result.pages_read,
        truncated=result.truncated,
    )


def _options(source: OpportunitySource, result: AdapterResult, observed_at):
    mapping: dict[tuple[str, str], OpportunityFilterOption] = {}
    for kind, values in (
        (OpportunityFilterKind.CATEGORY, result.category_labels),
        (OpportunityFilterKind.CITY, result.city_labels),
        (OpportunityFilterKind.COHORT, result.cohort_labels),
    ):
        replace_source_filter_options(
            source_id=source.id,
            kind=kind,
            values=values,
            observed_at=observed_at,
            complete=result.complete and not result.truncated,
        )
        for option in OpportunityFilterOption.objects.filter(
            kind=kind,
            source_observations__source=source,
            source_observations__active=True,
        ):
            mapping[(kind, option.normalized_label)] = option
    return mapping


def _candidate_options(candidate: CollectedOpportunity, mapping):
    result = []
    for kind, labels in (
        (OpportunityFilterKind.CATEGORY, candidate.category_labels),
        (OpportunityFilterKind.CITY, candidate.city_labels),
        (OpportunityFilterKind.COHORT, candidate.cohort_labels),
    ):
        for label in labels:
            _display, normalized = normalize_filter_label(label)
            try:
                result.append((kind, mapping[(kind, normalized)]))
            except KeyError:
                raise CollectionRejected(
                    "opportunities.adapter_filter_unknown.v1"
                ) from None
    return result


def _evidence(source: OpportunitySource, candidate: CollectedOpportunity, observed_at):
    value = (
        f"{source.company_name}官方招聘来源于{observed_at.date().isoformat()}采集，"
        f"公开岗位为{candidate.title}。"
    )
    return value[:1200]


def _replace_collected_assignments(row, candidate_options) -> None:
    grouped = {
        OpportunityFilterKind.CATEGORY: [],
        OpportunityFilterKind.CITY: [],
        OpportunityFilterKind.COHORT: [],
    }
    for kind, option in candidate_options:
        grouped[kind].append(option)
    overrides = {
        OpportunityFilterKind.CATEGORY: row.category_overridden,
        OpportunityFilterKind.CITY: row.city_overridden,
        OpportunityFilterKind.COHORT: row.cohort_overridden,
    }
    for kind, options in grouped.items():
        if overrides[kind]:
            continue
        row.filter_assignments.filter(
            option__kind=kind,
            origin=OpportunityFilterAssignment.Origin.COLLECTED,
        ).delete()
        OpportunityFilterAssignment.objects.bulk_create(
            [
                OpportunityFilterAssignment(
                    opportunity=row,
                    option=option,
                    origin=OpportunityFilterAssignment.Origin.COLLECTED,
                )
                for option in options
            ]
        )


def _apply_candidate(source, candidate, options, observed_at):
    identity_url, identity_title, identity_key = _candidate_identity(candidate)
    row = (
        Opportunity.objects.select_for_update()
        .filter(
            source=source,
            identity_key=identity_key,
            normalized_target_url=identity_url,
            normalized_identity_title=identity_title,
        )
        .first()
    )
    evidence = _evidence(source, candidate, observed_at)
    if row is None:
        row = Opportunity.objects.create(
            source=source,
            title=candidate.title,
            target_url=candidate.target_url,
            normalized_target_url=candidate.target_url,
            normalized_identity_title=identity_title,
            identity_key=identity_key,
            recruitment_type=candidate.recruitment_type,
            plan=candidate.plan,
            location_text=candidate.location_text,
            public_evidence=evidence,
            verification_status=Opportunity.VerificationStatus.PENDING,
            publication_state=Opportunity.PublicationState.PUBLISHED,
            origin=Opportunity.Origin.CRAWLER,
            last_collected_at=observed_at,
        )
        _replace_collected_assignments(row, options)
        OpportunityReviewItem.objects.create(
            opportunity=row,
            kind=OpportunityReviewItem.Kind.NEW,
            state=OpportunityReviewItem.State.OPEN,
            field_changes={"origin": "CRAWLER"},
        )
        return row, True, False

    changes = []
    for field, value, overridden in (
        ("title", candidate.title, row.title_overridden),
        ("target_url", candidate.target_url, row.target_url_overridden),
        (
            "recruitment_type",
            candidate.recruitment_type,
            row.recruitment_type_overridden,
        ),
        ("plan", candidate.plan, row.plan_overridden),
        ("location_text", candidate.location_text, row.location_overridden),
        ("public_evidence", evidence, row.public_evidence_overridden),
    ):
        if getattr(row, field) != value:
            changes.append(field)
            if not overridden:
                setattr(row, field, value)
    row.last_collected_at = observed_at
    row.list_missing = False
    row.list_missing_count = 0
    row.save(
        update_fields=(
            "title",
            "target_url",
            "recruitment_type",
            "plan",
            "location_text",
            "public_evidence",
            "last_collected_at",
            "list_missing",
            "list_missing_count",
            "updated_at",
        )
    )
    _replace_collected_assignments(row, options)
    if changes:
        OpportunityReviewItem.objects.update_or_create(
            opportunity=row,
            kind=OpportunityReviewItem.Kind.FIELD_CHANGE,
            state=OpportunityReviewItem.State.OPEN,
            defaults={"field_changes": {"fields": sorted(changes)}},
        )
    return row, False, bool(changes)


def _digest(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def record_collection_snapshot(
    *,
    source,
    source_check,
    result: AdapterResult,
    applied: CollectionApplyResult,
    observed_at,
) -> OpportunityCollectionSnapshot:
    identities = sorted(_candidate_identity(item)[2] for item in result.opportunities)
    fields = {
        _candidate_identity(item)[2]: _digest(
            {
                "title": item.title,
                "recruitment_type": item.recruitment_type,
                "plan": item.plan,
                "location_text": item.location_text,
                "categories": item.category_labels,
                "cities": item.city_labels,
                "cohorts": item.cohort_labels,
            }
        )
        for item in result.opportunities
    }
    return OpportunityCollectionSnapshot.objects.create(
        source=source,
        source_check=source_check,
        complete=result.complete,
        truncated=result.truncated,
        opportunity_identity_hashes=identities,
        opportunity_field_hashes=fields,
        category_labels=list(result.category_labels),
        city_labels=list(result.city_labels),
        cohort_labels=list(result.cohort_labels),
        difference_summary={
            "created": applied.created,
            "changed": applied.changed,
            "missing": applied.missing,
            "skipped": applied.skipped,
        },
        observed_at=observed_at,
        expires_at=observed_at + timedelta(days=90),
    )


def apply_adapter_result(
    *,
    source_id,
    result: AdapterResult,
    observed_at,
) -> CollectionApplyResult:
    with transaction.atomic():
        source = (
            OpportunitySource.objects.select_for_update()
            .prefetch_related("allowed_hosts")
            .get(pk=source_id)
        )
        allowed_hosts = frozenset(row.hostname for row in source.allowed_hosts.all())
        validated = validate_adapter_result(
            result,
            source=source,
            allowed_hosts=allowed_hosts,
            observed_at=observed_at,
        )
        options = _options(source, validated, observed_at)
        seen = set()
        created = 0
        changed = 0
        for candidate in validated.opportunities:
            candidate_options = _candidate_options(candidate, options)
            row, was_created, was_changed = _apply_candidate(
                source,
                candidate,
                candidate_options,
                observed_at,
            )
            seen.add(row.id)
            created += int(was_created)
            changed += int(was_changed)

        missing = 0
        if validated.complete and not validated.truncated:
            existing_rows = Opportunity.objects.select_for_update().filter(
                source=source
            )
            for row in existing_rows.exclude(id__in=seen):
                was_missing = row.list_missing
                row.list_missing_count += 1
                if row.list_missing_count >= 2:
                    row.list_missing = True
                    missing += int(not was_missing)
                    OpportunityReviewItem.objects.update_or_create(
                        opportunity=row,
                        kind=OpportunityReviewItem.Kind.LIST_MISSING,
                        state=OpportunityReviewItem.State.OPEN,
                        defaults={"field_changes": {"list_missing": True}},
                    )
                row.save(
                    update_fields=("list_missing_count", "list_missing", "updated_at")
                )
        return CollectionApplyResult(created, changed, missing, 0)


__all__ = [
    "CollectionApplyResult",
    "CollectionRejected",
    "apply_adapter_result",
    "record_collection_snapshot",
    "validate_adapter_result",
]
