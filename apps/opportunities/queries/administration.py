from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from apps.accounts.public import is_administrator
from apps.core.pagination import page_window

from ..checks.adapters import registered_adapters
from ..defaults import project_default_filters
from ..models import (
    Opportunity,
    OpportunityCheckRun,
    OpportunityCheckRunSource,
    OpportunityCollectionSnapshot,
    OpportunityFilterAssignment,
    OpportunityFilterKind,
    OpportunityFilterOption,
    OpportunityReviewItem,
    OpportunitySource,
)


@dataclass(frozen=True, slots=True)
class AdminPage:
    items: tuple
    page: int
    pages: int
    total: int
    page_size: int

    # Compatibility surface for the shared article-index pagination partial.
    # Existing opportunity callers keep their concise page/pages/total names.
    @property
    def page_number(self) -> int:
        return self.page

    @property
    def total_pages(self) -> int:
        return self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page, self.pages)


@dataclass(frozen=True, slots=True)
class AdminOptionItem:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class AdminOptionPage:
    items: tuple[AdminOptionItem, ...]
    page: int
    pages: int
    total: int
    page_size: int
    has_previous: bool
    has_next: bool


@dataclass(frozen=True, slots=True)
class AdminSourceItem:
    source_id: UUID
    company_name: str
    source_type: str
    official_url: str
    adapter_key: str
    enabled: bool
    publicly_visible: bool
    check_state: str
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error_code: str
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class AdminOpportunityItem:
    opportunity_id: UUID
    company_name: str
    source_id: UUID
    source_type: str
    title: str
    target_url: str
    recruitment_type: str
    plan: str
    location_text: str
    verification_status: str
    publication_state: str
    origin: str
    list_missing: bool
    last_checked_at: datetime | None
    last_success_at: datetime | None
    categories: tuple[str, ...]
    cities: tuple[str, ...]
    cohorts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminReviewItem:
    review_id: str
    opportunity_id: UUID
    company_name: str
    title: str
    kind: str
    state: str
    field_changes: dict
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminCheckRunItem:
    run_id: str
    kind: str
    trigger: str
    state: str
    total_sources: int
    succeeded_sources: int
    failed_sources: int
    truncated_sources: int
    skipped_sources: int
    not_executed_sources: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdminCheckRunSourceItem:
    source_run_id: int
    run_id: str
    run_kind_label: str
    trigger_label: str
    run_state: str
    source_id: UUID
    company_name: str
    source_type_label: str
    official_url: str
    state: str
    state_label: str
    opportunity_checks: int
    created_opportunities: int
    changed_opportunities: int
    missing_opportunities: int
    failed_opportunity_checks: int
    safe_error_code: str
    started_at: datetime | None
    completed_at: datetime | None
    can_cancel: bool


@dataclass(frozen=True, slots=True)
class AdminCheckRunChangeItem:
    kind: str
    kind_label: str
    opportunity_id: UUID
    title: str
    target_url: str
    recruitment_type_label: str
    location_text: str


@dataclass(frozen=True, slots=True)
class AdminCheckRunSourceDetail:
    item: AdminCheckRunSourceItem
    changes: tuple[AdminCheckRunChangeItem, ...]
    change_total: int
    changes_truncated: bool
    snapshot_observed_at: datetime | None
    detail_note: str


@dataclass(frozen=True, slots=True)
class AdminSettingsItem:
    default_city_ids: tuple[UUID, ...]
    default_verification_statuses: tuple[str, ...]
    default_source_ids: tuple[UUID, ...]
    default_recruitment_types: tuple[str, ...]
    default_category_ids: tuple[UUID, ...]
    default_cohort_ids: tuple[UUID, ...]
    row_version: int


@dataclass(frozen=True, slots=True)
class AdminSourceDetail:
    item: AdminSourceItem
    note: str
    respect_robots_txt: bool
    request_interval_seconds: int
    max_pages: int
    max_opportunities: int
    max_duration_seconds: int
    allowed_hosts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminOpportunityDetail:
    item: AdminOpportunityItem
    public_evidence: str
    category_ids: tuple[UUID, ...]
    city_ids: tuple[UUID, ...]
    cohort_ids: tuple[UUID, ...]


def _page(
    queryset,
    *,
    page: int,
    page_size: int,
    item_factory: Callable[[object], object] | None = None,
) -> AdminPage:
    page_size = page_size if page_size in (10, 20, 50) else 20
    page_number = page if isinstance(page, int) and page >= 1 else 1
    result = Paginator(queryset, page_size).get_page(page_number)
    page_rows = result.object_list
    items = (
        tuple(item_factory(row) for row in page_rows)
        if item_factory is not None
        else tuple(page_rows)
    )
    return AdminPage(
        items,
        result.number,
        result.paginator.num_pages,
        result.paginator.count,
        page_size,
    )


def _option_page(
    queryset,
    *,
    page: int,
    page_size: int,
    label_field: str = "label",
) -> AdminOptionPage:
    page_size = page_size if page_size in (20, 40, 50) else 40
    page_number = page if isinstance(page, int) and page >= 1 else 1
    result = Paginator(queryset, page_size).get_page(page_number)
    return AdminOptionPage(
        tuple(
            AdminOptionItem(str(row[0]), row[1])
            for row in result.object_list.values_list("id", label_field)
        ),
        result.number,
        result.paginator.num_pages,
        result.paginator.count,
        page_size,
        result.has_previous(),
        result.has_next(),
    )


def _option_page_with_selected(
    queryset,
    *,
    selected_queryset,
    selected: tuple[UUID, ...],
    page: int,
    page_size: int,
    label_field: str,
) -> AdminOptionPage:
    """Keep selected values visible while paginating the remaining options."""
    if not selected:
        return _option_page(
            queryset,
            page=page,
            page_size=page_size,
            label_field=label_field,
        )
    selected_items = tuple(
        AdminOptionItem(str(row[0]), row[1])
        for row in selected_queryset.values_list("id", label_field)
    )
    remaining = queryset.exclude(pk__in=selected)
    remaining_page = _option_page(
        remaining,
        page=page,
        page_size=page_size,
        label_field=label_field,
    )
    total = remaining_page.total + len(selected_items)
    # Selected values are pinned to page one and do not consume an additional
    # page. The remaining queryset already provides the correct page window
    # for the "load more" control, including when many values are selected.
    pages = max(1, remaining_page.pages)
    items = (
        selected_items + remaining_page.items
        if remaining_page.page == 1
        else remaining_page.items
    )
    return AdminOptionPage(
        items,
        remaining_page.page,
        pages,
        total,
        remaining_page.page_size,
        remaining_page.has_previous,
        remaining_page.has_next,
    )


def _administrator(actor_id) -> None:
    if not is_administrator(actor_id):
        raise PermissionError("Administrator access is required")


def _admin_source_item(row) -> AdminSourceItem:
    return AdminSourceItem(
        row.id,
        row.company_name,
        row.source_type,
        row.official_url,
        row.adapter_key,
        row.enabled,
        row.publicly_visible,
        row.check_state,
        row.last_checked_at,
        row.last_success_at,
        row.last_error_code,
        row.opportunity_count,
    )


_FILTER_OVERRIDE_FIELDS = {
    OpportunityFilterKind.CATEGORY: "category_overridden",
    OpportunityFilterKind.CITY: "city_overridden",
    OpportunityFilterKind.COHORT: "cohort_overridden",
}
_MAX_SELECTED_OPTIONS = 200


def _effective_assignments(row, assignments, kind):
    overridden = getattr(row, _FILTER_OVERRIDE_FIELDS[kind])
    return tuple(
        item
        for item in assignments
        if item.option.kind == kind
        and (not overridden or item.origin == OpportunityFilterAssignment.Origin.MANUAL)
    )


def _assignment_labels(row, assignments, kind):
    return tuple(
        item.option.label for item in _effective_assignments(row, assignments, kind)
    )


def _admin_opportunity_item(row, *, assignments=None) -> AdminOpportunityItem:
    assignments = (
        tuple(row.filter_assignments.all()) if assignments is None else assignments
    )
    return AdminOpportunityItem(
        row.id,
        row.source.company_name,
        row.source_id,
        row.source.source_type,
        row.title,
        row.target_url,
        row.recruitment_type,
        row.plan,
        row.location_text,
        row.verification_status,
        row.publication_state,
        row.origin,
        row.list_missing,
        row.last_checked_at,
        row.last_success_at,
        _assignment_labels(row, assignments, OpportunityFilterKind.CATEGORY),
        _assignment_labels(row, assignments, OpportunityFilterKind.CITY),
        _assignment_labels(row, assignments, OpportunityFilterKind.COHORT),
    )


def _admin_review_item(row) -> AdminReviewItem:
    return AdminReviewItem(
        row.id,
        row.opportunity_id,
        row.opportunity.source.company_name,
        row.opportunity.title,
        row.kind,
        row.state,
        row.field_changes,
        row.created_at,
    )


def _admin_check_run_item(row) -> AdminCheckRunItem:
    return AdminCheckRunItem(
        row.id,
        row.kind,
        row.trigger,
        row.state,
        row.total_sources,
        row.succeeded_sources,
        row.failed_sources,
        row.truncated_sources,
        row.skipped_sources,
        row.not_executed_sources,
        row.created_at,
        row.started_at,
        row.completed_at,
    )


def _admin_check_run_source_item(row) -> AdminCheckRunSourceItem:
    cancellable_states = {
        OpportunityCheckRun.State.PENDING,
        OpportunityCheckRun.State.RUNNING,
    }
    cancellation_states = {
        OpportunityCheckRun.State.CANCEL_REQUESTED,
        OpportunityCheckRun.State.CANCELLED,
    }
    state = row.run.state if row.run.state in cancellation_states else row.state
    state_label = (
        row.run.get_state_display()
        if row.run.state in cancellation_states
        else row.get_state_display()
    )
    return AdminCheckRunSourceItem(
        row.id,
        row.run_id,
        row.run.get_kind_display(),
        row.run.get_trigger_display(),
        row.run.state,
        row.source_id,
        row.source.company_name,
        row.source.get_source_type_display(),
        row.source.official_url,
        state,
        state_label,
        row.opportunity_checks,
        row.created_opportunities,
        row.changed_opportunities,
        row.missing_opportunities,
        row.failed_opportunity_checks,
        row.safe_error_code,
        row.started_at,
        row.completed_at,
        row.run.state in cancellable_states
        and row.id == row.cancel_anchor_source_run_id,
    )


def _snapshot_identity_set(value) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        identity
        for identity in value
        if isinstance(identity, str) and len(identity) == 64
    }


def _snapshot_field_hashes(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        identity: field_hash
        for identity, field_hash in value.items()
        if isinstance(identity, str)
        and len(identity) == 64
        and isinstance(field_hash, str)
    }


def _change_rows(*, source_id, identities, kind, limit):
    if limit <= 0 or not identities:
        return ()
    rows = Opportunity.objects.filter(
        source_id=source_id,
        identity_key__in=identities,
    ).order_by("title", "id")[:limit]
    label = "新增" if kind == "CREATED" else "更新"
    return tuple(
        AdminCheckRunChangeItem(
            kind,
            label,
            row.id,
            row.title,
            row.target_url,
            row.get_recruitment_type_display(),
            row.location_text,
        )
        for row in rows
    )


def admin_sources(
    *,
    actor_id,
    query="",
    enabled="",
    source_type="",
    check_state="",
    page=1,
    page_size=20,
) -> AdminPage:
    _administrator(actor_id)
    rows = OpportunitySource.objects.annotate(
        opportunity_count=Count("opportunities")
    ).order_by("normalized_company_name", "source_type", "id")
    if query:
        term = str(query).strip()
        rows = rows.filter(
            Q(company_name__icontains=term) | Q(official_url__icontains=term)
        )
    if enabled in {"true", "false"}:
        rows = rows.filter(enabled=(enabled == "true"))
    if source_type:
        rows = rows.filter(source_type=source_type)
    if check_state:
        rows = rows.filter(check_state=check_state)
    return _page(
        rows,
        page=page,
        page_size=page_size,
        item_factory=_admin_source_item,
    )


def admin_source_detail(*, actor_id, source_id) -> AdminSourceDetail | None:
    _administrator(actor_id)
    row = (
        OpportunitySource.objects.prefetch_related("allowed_hosts")
        .annotate(opportunity_count=Count("opportunities"))
        .filter(pk=source_id)
        .first()
    )
    if row is None:
        return None
    return AdminSourceDetail(
        _admin_source_item(row),
        row.note,
        row.respect_robots_txt,
        row.request_interval_seconds,
        row.max_pages,
        row.max_opportunities,
        row.max_duration_seconds,
        tuple(host.hostname for host in row.allowed_hosts.all()),
    )


def admin_opportunities(
    *,
    actor_id,
    query="",
    verification_status="",
    publication_state="",
    source_id="",
    recruitment_type="",
    origin="",
    category_ids=(),
    city_ids=(),
    cohort_ids=(),
    list_missing="",
    page=1,
    page_size=20,
) -> AdminPage:
    _administrator(actor_id)
    rows = (
        Opportunity.objects.select_related("source")
        .prefetch_related("filter_assignments__option")
        .order_by("source__normalized_company_name", "title", "id")
    )
    if query:
        term = str(query).strip()
        rows = rows.filter(
            Q(title__icontains=term)
            | Q(source__company_name__icontains=term)
            | Q(plan__icontains=term)
            | Q(location_text__icontains=term)
            | Q(public_evidence__icontains=term)
        )
    for field, values in (
        ("verification_status", verification_status),
        ("publication_state", publication_state),
        ("source_id", source_id),
        ("recruitment_type", recruitment_type),
        ("origin", origin),
    ):
        if values:
            rows = rows.filter(**{f"{field}__in": values})
    has_assignment_filter = False
    for kind, values in (
        (OpportunityFilterKind.CATEGORY, category_ids),
        (OpportunityFilterKind.CITY, city_ids),
        (OpportunityFilterKind.COHORT, cohort_ids),
    ):
        if values:
            has_assignment_filter = True
            rows = rows.filter(
                filter_assignments__option_id__in=values,
                filter_assignments__option__kind=kind,
            )
    if list_missing:
        rows = rows.filter(
            list_missing__in=tuple(value == "true" for value in list_missing)
        )
    if has_assignment_filter:
        rows = rows.distinct()
    return _page(
        rows,
        page=page,
        page_size=page_size,
        item_factory=_admin_opportunity_item,
    )


def admin_opportunity_detail(
    *, actor_id, opportunity_id
) -> AdminOpportunityDetail | None:
    _administrator(actor_id)
    row = (
        Opportunity.objects.select_related("source")
        .prefetch_related("filter_assignments__option")
        .filter(pk=opportunity_id)
        .first()
    )
    if row is None:
        return None
    assignments = tuple(row.filter_assignments.all())
    return AdminOpportunityDetail(
        _admin_opportunity_item(row, assignments=assignments),
        row.public_evidence,
        tuple(
            item.option_id
            for item in _effective_assignments(
                row, assignments, OpportunityFilterKind.CATEGORY
            )
        ),
        tuple(
            item.option_id
            for item in _effective_assignments(
                row, assignments, OpportunityFilterKind.CITY
            )
        ),
        tuple(
            item.option_id
            for item in _effective_assignments(
                row, assignments, OpportunityFilterKind.COHORT
            )
        ),
    )


def admin_review_queue(*, actor_id, state="OPEN", page=1, page_size=20) -> AdminPage:
    _administrator(actor_id)
    # Prefetch after the paginator has sliced the review rows. Joining the
    # two large opportunity tables before sorting makes PostgreSQL scan and
    # hash the entire catalogue even when the UI only needs 20 reviews.
    rows = OpportunityReviewItem.objects.prefetch_related(
        "opportunity__source"
    ).order_by("created_at", "id")
    if state:
        rows = rows.filter(state=state)
    return _page(
        rows,
        page=page,
        page_size=page_size,
        item_factory=_admin_review_item,
    )


def admin_check_runs(*, actor_id, page=1, page_size=20) -> AdminPage:
    _administrator(actor_id)
    rows = OpportunityCheckRun.objects.order_by("-created_at", "-id")
    return _page(
        rows,
        page=page,
        page_size=page_size,
        item_factory=_admin_check_run_item,
    )


def _admin_check_run_source_rows():
    running_source_run = (
        OpportunityCheckRunSource.objects.filter(
            run_id=OuterRef("run_id"),
            state=OpportunityCheckRunSource.State.RUNNING,
        )
        .order_by("position", "id")
        .values("id")[:1]
    )
    pending_source_run = (
        OpportunityCheckRunSource.objects.filter(
            run_id=OuterRef("run_id"),
            state=OpportunityCheckRunSource.State.PENDING,
        )
        .order_by("position", "id")
        .values("id")[:1]
    )
    return OpportunityCheckRunSource.objects.select_related("run", "source").annotate(
        cancel_anchor_source_run_id=Coalesce(
            Subquery(running_source_run),
            Subquery(pending_source_run),
        )
    )


def admin_check_run_sources(*, actor_id, page=1, page_size=20) -> AdminPage:
    _administrator(actor_id)
    rows = _admin_check_run_source_rows().order_by(
        "-run__created_at", "-run_id", "position", "id"
    )
    return _page(
        rows,
        page=page,
        page_size=page_size,
        item_factory=_admin_check_run_source_item,
    )


def admin_check_run_source_detail(
    *, actor_id, source_run_id, change_limit=200
) -> AdminCheckRunSourceDetail | None:
    _administrator(actor_id)
    if isinstance(source_run_id, bool):
        return None
    try:
        identity = int(source_run_id)
    except (TypeError, ValueError):
        return None
    if identity < 1:
        return None
    row = _admin_check_run_source_rows().filter(pk=identity).first()
    if row is None:
        return None
    item = _admin_check_run_source_item(row)
    snapshot = None
    if row.run.task_run_id:
        snapshot = (
            OpportunityCollectionSnapshot.objects.filter(
                source_id=row.source_id,
                source_check__task_run_id=row.run.task_run_id,
            )
            .order_by("-observed_at", "-id")
            .first()
        )
    if snapshot is None:
        has_changes = bool(
            row.created_opportunities
            or row.changed_opportunities
            or row.missing_opportunities
        )
        note = (
            "这次任务的逐岗位明细尚未生成或已超过 90 天保留期。"
            if has_changes
            else "这次任务没有新增或更新岗位。"
        )
        return AdminCheckRunSourceDetail(item, (), 0, False, None, note)

    previous = (
        OpportunityCollectionSnapshot.objects.filter(
            source_id=row.source_id,
            observed_at__lt=snapshot.observed_at,
        )
        .order_by("-observed_at", "-id")
        .first()
    )
    current_identities = _snapshot_identity_set(snapshot.opportunity_identity_hashes)
    current_fields = _snapshot_field_hashes(snapshot.opportunity_field_hashes)
    if previous is None:
        if row.created_opportunities == len(current_identities):
            created_identities = current_identities
            changed_identities = set()
            detail_note = ""
        elif row.created_opportunities or row.changed_opportunities:
            created_identities = set()
            changed_identities = set()
            detail_note = "缺少上一份采集快照，无法恢复这次任务的逐岗位差异。"
        else:
            created_identities = set()
            changed_identities = set()
            detail_note = "这次任务没有新增或更新岗位。"
    else:
        previous_identities = _snapshot_identity_set(
            previous.opportunity_identity_hashes
        )
        previous_fields = _snapshot_field_hashes(previous.opportunity_field_hashes)
        created_identities = current_identities - previous_identities
        changed_identities = {
            identity
            for identity in current_identities & previous_identities
            if current_fields.get(identity) != previous_fields.get(identity)
        }
        detail_note = (
            ""
            if created_identities or changed_identities
            else "这次任务没有新增或更新岗位。"
        )

    change_limit = max(1, min(int(change_limit), 200))
    changes = list(
        _change_rows(
            source_id=row.source_id,
            identities=created_identities,
            kind="CREATED",
            limit=change_limit,
        )
    )
    changes.extend(
        _change_rows(
            source_id=row.source_id,
            identities=changed_identities,
            kind="CHANGED",
            limit=change_limit - len(changes),
        )
    )
    change_total = len(created_identities) + len(changed_identities)
    return AdminCheckRunSourceDetail(
        item,
        tuple(changes),
        change_total,
        len(changes) < change_total,
        snapshot.observed_at,
        detail_note,
    )


def _selected_uuids(values) -> tuple[UUID, ...]:
    selected: list[UUID] = []
    for value in values or ():
        if len(selected) >= _MAX_SELECTED_OPTIONS:
            break
        try:
            identity = UUID(str(value))
        except (TypeError, ValueError):
            continue
        if identity not in selected:
            selected.append(identity)
    return tuple(selected)


def admin_filter_option_page(
    *,
    actor_id,
    kind: str,
    query: str = "",
    page: int = 1,
    page_size: int = 40,
    selected_ids=(),
    active_only: bool = True,
) -> AdminOptionPage:
    """Return a bounded page of filter options for admin pickers.

    Selected values are kept in the result even when they are outside the
    current search page. This lets a picker preserve an existing manual value
    while the rest of the option catalogue remains on-demand.
    """
    _administrator(actor_id)
    if kind not in OpportunityFilterKind.values:
        raise ValueError("Invalid opportunity filter kind")
    selected = _selected_uuids(selected_ids)
    term = " ".join(str(query).split())[:100]
    rows = OpportunityFilterOption.objects.filter(kind=kind)
    if active_only:
        rows = rows.filter(Q(source_observations__active=True) | Q(pk__in=selected))
    selected_rows = rows.filter(pk__in=selected)
    if term:
        rows = rows.filter(Q(label__icontains=term) | Q(pk__in=selected))
    rows = rows.distinct().order_by("normalized_label", "id")
    return _option_page_with_selected(
        rows,
        selected_queryset=selected_rows.distinct().order_by("normalized_label", "id"),
        selected=selected,
        page=page,
        page_size=page_size,
        label_field="label",
    )


def admin_source_option_page(
    *,
    actor_id,
    query: str = "",
    page: int = 1,
    page_size: int = 40,
    selected_ids=(),
    public_only: bool = False,
) -> AdminOptionPage:
    """Return a bounded page of source choices for admin pickers."""
    _administrator(actor_id)
    selected = _selected_uuids(selected_ids)
    term = " ".join(str(query).split())[:120]
    rows = OpportunitySource.objects.all()
    if public_only:
        rows = rows.filter(enabled=True, publicly_visible=True)
    selected_rows = rows.filter(pk__in=selected)
    if term:
        rows = rows.filter(
            Q(company_name__icontains=term)
            | Q(official_url__icontains=term)
            | Q(pk__in=selected)
        )
    rows = rows.order_by("normalized_company_name", "source_type", "id")
    return _option_page_with_selected(
        rows,
        selected_queryset=selected_rows.order_by(
            "normalized_company_name", "source_type", "id"
        ),
        selected=selected,
        page=page,
        page_size=page_size,
        label_field="company_name",
    )


def admin_filter_options(
    *, actor_id, kind: str, active_only: bool = True
) -> tuple[OpportunityFilterOption, ...]:
    _administrator(actor_id)
    rows = OpportunityFilterOption.objects.filter(kind=kind)
    if active_only:
        rows = rows.filter(source_observations__active=True).distinct()
    return tuple(rows.order_by("normalized_label", "id"))


def admin_source_choices(*, actor_id) -> tuple[tuple[str, str], ...]:
    _administrator(actor_id)
    return tuple(
        (str(row.id), f"{row.company_name} · {row.get_source_type_display()}")
        for row in OpportunitySource.objects.order_by(
            "normalized_company_name", "source_type", "id"
        )
    )


def admin_adapter_choices(*, actor_id) -> tuple[tuple[str, str], ...]:
    _administrator(actor_id)
    labels = {
        "manual-unsupported-v1": "暂不支持自动采集",
        "antgroup-v1": "蚂蚁集团校园招聘门户",
        "beisen-zhiye-v1": "北森招聘门户",
        "brainco-v1": "强脑科技招聘门户",
        "czbank-v1": "浙商银行招聘门户",
        "dahua-v1": "大华招聘门户",
        "getui-v1": "每日互动招聘门户",
        "hzbank-v1": "杭州银行招聘门户",
        "huawei-v1": "华为校园招聘门户",
        "jd-campus-v1": "京东校园招聘门户",
        "kujiale-v1": "酷家乐招聘门户",
        "meituan-v1": "美团招聘门户",
        "netease-game-v1": "网易互娱招聘门户",
        "tencent-v1": "腾讯校园招聘门户",
        "unitree-v1": "宇树科技招聘门户",
    }
    return tuple((key, labels.get(key, key)) for key in sorted(registered_adapters()))


def admin_settings(*, actor_id) -> AdminSettingsItem:
    _administrator(actor_id)
    from ..models import OpportunitySettings

    row = (
        OpportunitySettings.objects.prefetch_related("default_filter_selections")
        .filter(pk=1)
        .first()
    )
    defaults = project_default_filters(
        row.default_filter_selections.all() if row else (),
        settings_exists=row is not None,
    )
    return AdminSettingsItem(
        defaults.city_ids,
        defaults.verification_statuses,
        defaults.source_ids,
        defaults.recruitment_types,
        defaults.category_ids,
        defaults.cohort_ids,
        row.row_version if row else 0,
    )


def admin_open_review_count(*, actor_id) -> int:
    _administrator(actor_id)
    return OpportunityReviewItem.objects.filter(state="OPEN").count()


def admin_attention_counts(*, actor_id) -> tuple[int, int]:
    reviews = admin_open_review_count(actor_id=actor_id)
    failed_runs = OpportunityCheckRun.objects.filter(
        state__in=("PARTIAL", "FAILED", "TRUNCATED")
    ).count()
    return reviews, failed_runs


__all__ = [
    "AdminPage",
    "AdminOptionItem",
    "AdminOptionPage",
    "AdminSourceItem",
    "AdminOpportunityItem",
    "AdminReviewItem",
    "AdminCheckRunItem",
    "AdminCheckRunChangeItem",
    "AdminCheckRunSourceDetail",
    "AdminCheckRunSourceItem",
    "AdminSettingsItem",
    "AdminSourceDetail",
    "AdminOpportunityDetail",
    "admin_sources",
    "admin_opportunities",
    "admin_review_queue",
    "admin_check_runs",
    "admin_check_run_source_detail",
    "admin_check_run_sources",
    "admin_filter_options",
    "admin_filter_option_page",
    "admin_settings",
    "admin_source_detail",
    "admin_opportunity_detail",
    "admin_open_review_count",
    "admin_attention_counts",
    "admin_source_choices",
    "admin_source_option_page",
    "admin_adapter_choices",
]
