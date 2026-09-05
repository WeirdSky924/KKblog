from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from ipaddress import ip_address
from zoneinfo import ZoneInfo

from django.core.paginator import Paginator
from django.db.models import Q

from apps.core.pagination import PageSlice
from apps.operations.models import AuditEntry

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class AuditListItem:
    id: str
    trace_code: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    client_ip: str
    summary: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditDetail(AuditListItem):
    before_safe: dict[str, object]
    after_safe: dict[str, object]


def mask_ip(value: str) -> str:
    parsed = ip_address(value)
    if parsed.version == 4:
        parts = str(parsed).split(".")
        return ".".join((*parts[:3], "***"))
    return f"{parsed.exploded.split(':')[0]}:{parsed.exploded.split(':')[1]}:****:****"


def _bounds(start: date | None, end: date | None):
    if start and end and start > end:
        raise ValueError("Invalid audit time range")
    lower = (
        datetime.combine(start, time.min, SHANGHAI).astimezone(UTC) if start else None
    )
    upper = (
        datetime.combine(end + timedelta(days=1), time.min, SHANGHAI).astimezone(UTC)
        if end
        else None
    )
    return lower, upper


def search_audit(
    *,
    keyword: str = "",
    action: str = "",
    target_type: str = "",
    target_id: str = "",
    start: date | None = None,
    end: date | None = None,
    is_admin: bool,
    limit: int = 100,
    page: int | None = None,
    page_size: int = 20,
) -> list[AuditListItem] | PageSlice[AuditListItem]:
    if not is_admin:
        raise PermissionError("Audit access denied")
    if not 1 <= limit <= 200:
        raise ValueError("Invalid audit query limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid audit page")
    queryset = AuditEntry.objects.all()
    if keyword:
        term = keyword.strip()[:100]
        queryset = queryset.filter(
            Q(action__icontains=term)
            | Q(target_id__icontains=term)
            | Q(summary__icontains=term)
            | Q(trace_code__icontains=term)
        )
    if action:
        queryset = queryset.filter(action=action)
    if target_type:
        queryset = queryset.filter(target_type=target_type)
    if target_id:
        queryset = queryset.filter(target_id=target_id)
    lower, upper = _bounds(start, end)
    if lower:
        queryset = queryset.filter(created_at__gte=lower)
    if upper:
        queryset = queryset.filter(created_at__lt=upper)
    ordered = queryset.order_by("-created_at", "-id")

    def item(row):
        return AuditListItem(
            id=row.id,
            trace_code=row.trace_code,
            actor_id=str(row.actor_id),
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            client_ip=mask_ip(row.client_ip),
            summary=row.summary,
            created_at=row.created_at,
        )

    if page is None:
        return [item(row) for row in ordered[:limit]]
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(item(row) for row in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def audit_detail(*, entry_id: str, is_admin: bool) -> AuditDetail:
    if not is_admin:
        raise PermissionError("Audit access denied")
    row = AuditEntry.objects.get(pk=entry_id)
    return AuditDetail(
        id=row.id,
        trace_code=row.trace_code,
        actor_id=str(row.actor_id),
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        client_ip=row.client_ip,
        summary=row.summary,
        created_at=row.created_at,
        before_safe=row.before_safe,
        after_safe=row.after_safe,
    )
