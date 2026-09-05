from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Q

from apps.core.ids import normalize_ulid
from apps.core.pagination import PageSlice

from ..models import Report, ReportAppeal, ReportReason
from ..ports import ModerationAccountPolicy, default_moderation_account_policy


class AdminReportNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class AdminReportListItem:
    id: str
    target_comment_id: str
    reason: str
    reason_label: str
    state: str
    has_appeal: bool
    appeal_state: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminReportAppealDetail:
    id: str
    appellant_id: UUID
    basis_outcome: str
    statement: str
    state: str
    decision_reason: str
    recovery_error_code: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AdminReportDetail(AdminReportListItem):
    reporter_id: UUID
    reported_author_id: UUID | None
    description: str
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    decision_reason: str
    closure_reason: str
    appeal: AdminReportAppealDetail | None


def _actor(value, *, account_policy: ModerationAccountPolicy) -> UUID:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        raise PermissionError("Administrator report access denied") from None
    if not account_policy.is_active_account(
        actor
    ) or not account_policy.is_administrator(actor):
        raise PermissionError("Administrator report access denied")
    return actor


def _identity(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise AdminReportNotFound from None


def _appeal(report: Report) -> ReportAppeal | None:
    try:
        return report.appeal
    except ReportAppeal.DoesNotExist:
        return None


def _list_item(report: Report) -> AdminReportListItem:
    appeal = _appeal(report)
    return AdminReportListItem(
        id=report.id,
        target_comment_id=report.target_comment_id,
        reason=report.reason,
        reason_label=ReportReason(report.reason).label,
        state=report.state,
        has_appeal=appeal is not None,
        appeal_state=appeal.state if appeal is not None else None,
        created_at=report.created_at,
    )


def admin_report_list(
    *,
    actor_id,
    state: str = "",
    limit: int = 200,
    page: int | None = None,
    page_size: int = 20,
    account_policy: ModerationAccountPolicy | None = None,
) -> tuple[AdminReportListItem, ...] | PageSlice[AdminReportListItem]:
    accounts = account_policy or default_moderation_account_policy()
    _actor(actor_id, account_policy=accounts)
    if state and state not in Report.State.values:
        raise ValueError("Invalid administrator report state")
    if isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("Invalid administrator report limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid administrator report page")
    queryset = Report.objects.select_related("appeal")
    if state:
        queryset = queryset.filter(state=state)
    ordered = queryset.order_by("-created_at", "-id")
    if page is None:
        return tuple(_list_item(report) for report in ordered[:limit])
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(_list_item(report) for report in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def admin_report_review_count(
    *,
    actor_id,
    account_policy: ModerationAccountPolicy | None = None,
) -> int:
    accounts = account_policy or default_moderation_account_policy()
    _actor(actor_id, account_policy=accounts)
    return Report.objects.filter(
        Q(state=Report.State.PENDING)
        | Q(
            state=Report.State.APPEAL_PENDING,
            appeal__state=ReportAppeal.State.PENDING,
        )
    ).count()


def admin_report_detail(
    *,
    actor_id,
    report_id: str,
    account_policy: ModerationAccountPolicy | None = None,
) -> AdminReportDetail:
    accounts = account_policy or default_moderation_account_policy()
    _actor(actor_id, account_policy=accounts)
    report = (
        Report.objects.select_related("appeal").filter(pk=_identity(report_id)).first()
    )
    if report is None:
        raise AdminReportNotFound
    item = _list_item(report)
    appeal = _appeal(report)
    appeal_detail = None
    if appeal is not None:
        appeal_detail = AdminReportAppealDetail(
            id=appeal.id,
            appellant_id=appeal.appellant_id,
            basis_outcome=appeal.basis_outcome,
            statement=appeal.statement,
            state=appeal.state,
            decision_reason=appeal.decision_reason,
            recovery_error_code=appeal.recovery_error_code,
            created_at=appeal.created_at,
        )
    return AdminReportDetail(
        **{
            field: getattr(item, field)
            for field in AdminReportListItem.__dataclass_fields__
        },
        reporter_id=report.reporter_id,
        reported_author_id=report.reported_author_id,
        description=report.description,
        reviewed_by_id=report.reviewed_by_id,
        reviewed_at=report.reviewed_at,
        decision_reason=report.decision_reason,
        closure_reason=report.closure_reason,
        appeal=appeal_detail,
    )


__all__ = [
    "AdminReportAppealDetail",
    "AdminReportDetail",
    "AdminReportListItem",
    "AdminReportNotFound",
    "admin_report_detail",
    "admin_report_list",
    "admin_report_review_count",
]
