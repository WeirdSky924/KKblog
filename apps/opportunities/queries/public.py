from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    When,
)

from apps.core.pagination import page_window

from ..defaults import project_default_filters
from ..models import (
    Opportunity,
    OpportunityBookmark,
    OpportunityFilterAssignment,
    OpportunityFilterKind,
    OpportunityFilterOption,
    OpportunitySettings,
    OpportunitySource,
)
from ..policies import publicly_available_opportunity

PAGE_SIZES = (10, 20, 50)


@dataclass(frozen=True, slots=True)
class PublicOpportunityItem:
    opportunity_id: UUID
    company_name: str
    title: str
    target_url: str
    recruitment_type: str
    recruitment_type_label: str
    plan: str
    location_text: str
    public_evidence: str
    verification_status: str
    verification_status_label: str
    categories: tuple[str, ...]
    cities: tuple[str, ...]
    cohorts: tuple[str, ...]
    published_at: datetime | None
    availability_label: str
    bookmarked: bool = False


@dataclass(frozen=True, slots=True)
class PublicOpportunityPage:
    items: tuple[PublicOpportunityItem, ...]
    page_number: int = 1
    total_pages: int = 1
    total_count: int = 0
    page_size: int = 20
    has_previous: bool = False
    has_next: bool = False
    page_window: tuple[int | None, ...] = (1,)


@dataclass(frozen=True, slots=True)
class PublicOpportunitySourceItem:
    source_id: UUID
    company_name: str
    source_type: str
    source_type_label: str
    official_url: str
    last_success_at: datetime | None
    status_label: str
    public_opportunity_count: int


@dataclass(frozen=True, slots=True)
class PublicOpportunitySourcePage:
    items: tuple[PublicOpportunitySourceItem, ...]
    page_number: int = 1
    total_pages: int = 1
    total_count: int = 0
    page_size: int = 20
    has_previous: bool = False
    has_next: bool = False
    page_window: tuple[int | None, ...] = (1,)


@dataclass(frozen=True, slots=True)
class PublicFilterOption:
    option_id: UUID
    label: str


@dataclass(frozen=True, slots=True)
class PublicSourceOption:
    source_id: UUID
    label: str


@dataclass(frozen=True, slots=True)
class PublicOpportunityFilters:
    cities: tuple[PublicFilterOption, ...]
    categories: tuple[PublicFilterOption, ...]
    cohorts: tuple[PublicFilterOption, ...]
    sources: tuple[PublicSourceOption, ...]
    default_city_ids: tuple[UUID, ...]
    default_verification_statuses: tuple[str, ...]
    default_source_ids: tuple[UUID, ...]
    default_recruitment_types: tuple[str, ...]
    default_category_ids: tuple[UUID, ...]
    default_cohort_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class PublicOpportunitySummary:
    total: int
    confirmed: int
    pending: int
    sources: int


def _assignment_prefetch() -> Prefetch:
    return Prefetch(
        "filter_assignments",
        queryset=OpportunityFilterAssignment.objects.select_related("option").order_by(
            "option__kind", "option__normalized_label", "option_id"
        ),
        to_attr="public_filter_assignments",
    )


def _labels(row: Opportunity, kind: str, *, overridden: bool) -> tuple[str, ...]:
    return tuple(
        assignment.option.label
        for assignment in row.public_filter_assignments
        if assignment.option.kind == kind
        and (
            not overridden
            or assignment.origin == OpportunityFilterAssignment.Origin.MANUAL
        )
    )


def _availability(row: Opportunity) -> str:
    if row.publication_state == Opportunity.PublicationState.WITHDRAWN:
        return "已下架"
    if row.list_missing:
        return "已过期"
    if row.verification_status == Opportunity.VerificationStatus.EXPIRED:
        return "已过期"
    if not row.source.enabled or not row.source.publicly_visible:
        return "已下架"
    return "可申请"


def _item(row: Opportunity, bookmarks: frozenset[UUID]) -> PublicOpportunityItem:
    return PublicOpportunityItem(
        opportunity_id=row.id,
        company_name=row.source.company_name,
        title=row.title,
        target_url=row.target_url,
        recruitment_type=row.recruitment_type,
        recruitment_type_label=row.get_recruitment_type_display(),
        plan=row.plan,
        location_text=row.location_text,
        public_evidence=row.public_evidence,
        verification_status=row.verification_status,
        verification_status_label=row.get_verification_status_display(),
        categories=_labels(
            row,
            OpportunityFilterKind.CATEGORY,
            overridden=row.category_overridden,
        ),
        cities=_labels(
            row,
            OpportunityFilterKind.CITY,
            overridden=row.city_overridden,
        ),
        cohorts=_labels(
            row,
            OpportunityFilterKind.COHORT,
            overridden=row.cohort_overridden,
        ),
        published_at=row.published_at,
        availability_label=_availability(row),
        bookmarked=row.id in bookmarks,
    )


def _page(source, *, page: int, page_size: int):
    size = page_size if page_size in PAGE_SIZES else 20
    number = page if isinstance(page, int) and page >= 1 else 1
    result = Paginator(source, size).get_page(number)
    return result, page_window(result.number, result.paginator.num_pages)


def _actor(value) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _assignment_exists(
    *,
    kind: str,
    values=(),
    term: str | None = None,
    override_field: str | None = None,
):
    filters = {
        "opportunity_id": OuterRef("pk"),
        "option__kind": kind,
    }
    if values:
        filters["option_id__in"] = values
    if term:
        filters["option__label__icontains"] = term
    assignments = OpportunityFilterAssignment.objects.filter(**filters)
    if override_field:
        assignments = assignments.filter(
            Q(**{f"opportunity__{override_field}": False})
            | Q(origin=OpportunityFilterAssignment.Origin.MANUAL)
        )
    return Exists(assignments)


def _effective_assignment(values, *, kind: str, override_field: str) -> Q:
    return _assignment_exists(
        kind=kind,
        values=values,
        override_field=override_field,
    )


def _effective_label_search(term: str, *, kind: str, override_field: str) -> Q:
    return _assignment_exists(
        kind=kind,
        term=term,
        override_field=override_field,
    )


def public_opportunities(
    *,
    actor_id=None,
    query: str = "",
    city_ids=(),
    verification_statuses=(),
    source_ids=(),
    recruitment_types=(),
    category_ids=(),
    cohort_ids=(),
    bookmarked_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> PublicOpportunityPage:
    actor = _actor(actor_id)
    bookmarked_ids = (
        frozenset(
            OpportunityBookmark.objects.filter(account_id=actor).values_list(
                "opportunity_id", flat=True
            )
        )
        if actor
        else frozenset()
    )
    if bookmarked_only and actor:
        rows = Opportunity.objects.filter(id__in=bookmarked_ids)
    elif bookmarked_only:
        rows = Opportunity.objects.none()
    else:
        rows = Opportunity.objects.filter(publicly_available_opportunity())
    rows = rows.select_related("source").prefetch_related(_assignment_prefetch())
    term = " ".join(str(query).split())[:100]
    if term:
        rows = rows.filter(
            Q(title__icontains=term)
            | Q(source__company_name__icontains=term)
            | Q(plan__icontains=term)
            | Q(location_text__icontains=term)
            | Q(public_evidence__icontains=term)
            | _effective_label_search(
                term,
                kind=OpportunityFilterKind.CATEGORY,
                override_field="category_overridden",
            )
            | _effective_label_search(
                term,
                kind=OpportunityFilterKind.CITY,
                override_field="city_overridden",
            )
            | _effective_label_search(
                term,
                kind=OpportunityFilterKind.COHORT,
                override_field="cohort_overridden",
            )
        ).annotate(
            search_rank=Case(
                When(title__icontains=term, then=8),
                When(source__company_name__icontains=term, then=6),
                When(plan__icontains=term, then=5),
                When(location_text__icontains=term, then=4),
                When(public_evidence__icontains=term, then=2),
                default=1,
                output_field=IntegerField(),
            )
        )
    for values, kind, override in (
        (city_ids, OpportunityFilterKind.CITY, "city_overridden"),
        (category_ids, OpportunityFilterKind.CATEGORY, "category_overridden"),
        (cohort_ids, OpportunityFilterKind.COHORT, "cohort_overridden"),
    ):
        if values:
            rows = rows.filter(
                _effective_assignment(values, kind=kind, override_field=override)
            )
    if verification_statuses and not bookmarked_only:
        rows = rows.filter(verification_status__in=verification_statuses)
    if source_ids:
        rows = rows.filter(source_id__in=source_ids)
    if recruitment_types:
        rows = rows.filter(recruitment_type__in=recruitment_types)
    publication_order = F("published_at").desc(nulls_last=True)
    collection_order = F("last_collected_at").desc(nulls_last=True)
    ordering = (
        (
            "-search_rank",
            publication_order,
            collection_order,
            "source__normalized_company_name",
            "title",
            "id",
        )
        if term
        else (
            publication_order,
            collection_order,
            "source__normalized_company_name",
            "title",
            "id",
        )
    )
    result, window = _page(rows.order_by(*ordering), page=page, page_size=page_size)
    return PublicOpportunityPage(
        tuple(_item(row, bookmarked_ids) for row in result.object_list),
        result.number,
        result.paginator.num_pages,
        result.paginator.count,
        result.paginator.per_page,
        result.has_previous(),
        result.has_next(),
        window,
    )


def bookmarked_opportunities(*, account_id) -> PublicOpportunityPage:
    return public_opportunities(
        actor_id=account_id,
        bookmarked_only=True,
        page=1,
        page_size=50,
    )


def public_opportunity_sources(
    *, query: str = "", source_types=(), page: int = 1, page_size: int = 20
) -> PublicOpportunitySourcePage:
    rows = OpportunitySource.objects.filter(enabled=True, publicly_visible=True)
    term = " ".join(str(query).split())[:100]
    if term:
        rows = rows.filter(company_name__icontains=term)
    if source_types:
        rows = rows.filter(source_type__in=source_types)
    rows = rows.annotate(
        public_opportunity_count=Count(
            "opportunities",
            filter=Q(
                opportunities__publication_state="PUBLISHED",
                opportunities__verification_status__in=("CONFIRMED", "PENDING"),
                opportunities__list_missing=False,
            ),
        )
    ).order_by("normalized_company_name", "source_type", "id")
    result, window = _page(rows, page=page, page_size=page_size)
    items = tuple(
        PublicOpportunitySourceItem(
            source_id=row.id,
            company_name=row.company_name,
            source_type=row.source_type,
            source_type_label=row.get_source_type_display(),
            official_url=row.official_url,
            last_success_at=row.last_success_at,
            status_label=row.get_check_state_display(),
            public_opportunity_count=row.public_opportunity_count,
        )
        for row in result.object_list
    )
    return PublicOpportunitySourcePage(
        items,
        result.number,
        result.paginator.num_pages,
        result.paginator.count,
        result.paginator.per_page,
        result.has_previous(),
        result.has_next(),
        window,
    )


def public_opportunity_filters() -> PublicOpportunityFilters:
    def options(kind):
        rows = (
            OpportunityFilterOption.objects.filter(
                kind=kind,
                source_observations__active=True,
                source_observations__source__enabled=True,
                source_observations__source__publicly_visible=True,
            )
            .distinct()
            .order_by("normalized_label", "id")
        )
        return tuple(PublicFilterOption(row.id, row.label) for row in rows)

    sources = tuple(
        PublicSourceOption(row.id, row.company_name)
        for row in OpportunitySource.objects.filter(
            enabled=True, publicly_visible=True
        ).order_by("normalized_company_name", "source_type", "id")
    )
    settings = (
        OpportunitySettings.objects.prefetch_related("default_filter_selections")
        .filter(pk=1)
        .first()
    )
    city_options = options(OpportunityFilterKind.CITY)
    city_ids = {item.option_id for item in city_options}
    category_options = options(OpportunityFilterKind.CATEGORY)
    category_ids = {item.option_id for item in category_options}
    cohort_options = options(OpportunityFilterKind.COHORT)
    cohort_ids = {item.option_id for item in cohort_options}
    source_ids = {item.source_id for item in sources}
    defaults = project_default_filters(
        settings.default_filter_selections.all() if settings else (),
        settings_exists=settings is not None,
    )
    return PublicOpportunityFilters(
        city_options,
        category_options,
        cohort_options,
        sources,
        tuple(value for value in defaults.city_ids if value in city_ids),
        tuple(
            value
            for value in defaults.verification_statuses
            if value in Opportunity.VerificationStatus.values
        ),
        tuple(value for value in defaults.source_ids if value in source_ids),
        tuple(
            value
            for value in defaults.recruitment_types
            if value in Opportunity.RecruitmentType.values
        ),
        tuple(value for value in defaults.category_ids if value in category_ids),
        tuple(value for value in defaults.cohort_ids if value in cohort_ids),
    )


def public_opportunity_summary() -> PublicOpportunitySummary:
    rows = Opportunity.objects.filter(publicly_available_opportunity())
    counts = rows.aggregate(
        total=Count("id"),
        confirmed=Count("id", filter=Q(verification_status="CONFIRMED")),
        pending=Count("id", filter=Q(verification_status="PENDING")),
    )
    return PublicOpportunitySummary(
        counts["total"],
        counts["confirmed"],
        counts["pending"],
        OpportunitySource.objects.filter(enabled=True, publicly_visible=True).count(),
    )


__all__ = [
    "PAGE_SIZES",
    "PublicFilterOption",
    "PublicOpportunityFilters",
    "PublicOpportunityItem",
    "PublicOpportunityPage",
    "PublicOpportunitySourceItem",
    "PublicOpportunitySourcePage",
    "PublicOpportunitySummary",
    "PublicSourceOption",
    "bookmarked_opportunities",
    "public_opportunities",
    "public_opportunity_filters",
    "public_opportunity_sources",
    "public_opportunity_summary",
]
