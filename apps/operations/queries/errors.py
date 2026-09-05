import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.paginator import Paginator
from django.db.models import Q

from apps.core.pagination import PageSlice
from apps.operations.models import RuntimeError as RuntimeErrorRecord

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class RuntimeErrorListItem:
    id: str
    fingerprint: str
    error_code: str
    exception_type: str
    safe_summary: str
    latest_trace_code: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeErrorOccurrenceItem:
    trace_code: str
    safe_context: dict[str, object]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeErrorDetail(RuntimeErrorListItem):
    safe_traceback: str
    safe_context: dict[str, object]
    safe_context_json: str
    occurrences: tuple[RuntimeErrorOccurrenceItem, ...]


def _bounds(start: date | None, end: date | None):
    if start and end and start > end:
        raise ValueError("Invalid runtime-error time range")
    lower = (
        datetime.combine(start, time.min, SHANGHAI).astimezone(UTC) if start else None
    )
    upper = (
        datetime.combine(end + timedelta(days=1), time.min, SHANGHAI).astimezone(UTC)
        if end
        else None
    )
    return lower, upper


def _list_item(row: RuntimeErrorRecord) -> RuntimeErrorListItem:
    return RuntimeErrorListItem(
        id=row.id,
        fingerprint=row.fingerprint,
        error_code=row.error_code,
        exception_type=row.exception_type,
        safe_summary=row.safe_summary,
        latest_trace_code=row.latest_trace_code,
        occurrence_count=row.occurrence_count,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
    )


def search_runtime_errors(
    *,
    trace_code: str = "",
    error_code: str = "",
    keyword: str = "",
    start: date | None = None,
    end: date | None = None,
    is_admin: bool,
    limit: int = 100,
    page: int | None = None,
    page_size: int = 20,
) -> list[RuntimeErrorListItem] | PageSlice[RuntimeErrorListItem]:
    if not is_admin:
        raise PermissionError("Runtime-error access denied")
    if not 1 <= limit <= 200:
        raise ValueError("Invalid runtime-error query limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid runtime-error page")
    queryset = RuntimeErrorRecord.objects.all()
    if trace_code:
        queryset = queryset.filter(occurrences__trace_code=trace_code.strip()[:30])
    if error_code:
        queryset = queryset.filter(error_code=error_code.strip()[:96])
    if keyword:
        term = keyword.strip()[:100]
        queryset = queryset.filter(
            Q(exception_type__icontains=term)
            | Q(safe_summary__icontains=term)
            | Q(safe_traceback__icontains=term)
            | Q(fingerprint__icontains=term)
        )
    lower, upper = _bounds(start, end)
    if lower:
        queryset = queryset.filter(occurrences__occurred_at__gte=lower)
    if upper:
        queryset = queryset.filter(occurrences__occurred_at__lt=upper)
    ordered = queryset.distinct().order_by("-last_seen_at", "-id")
    if page is None:
        return [_list_item(row) for row in ordered[:limit]]
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(_list_item(row) for row in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def error_detail(*, error_id: str, is_admin: bool) -> RuntimeErrorDetail | None:
    if not is_admin:
        raise PermissionError("Runtime-error access denied")
    row = RuntimeErrorRecord.objects.filter(pk=error_id).first()
    if row is None:
        return None
    occurrences = tuple(
        RuntimeErrorOccurrenceItem(
            trace_code=item.trace_code,
            safe_context=item.safe_context,
            occurred_at=item.occurred_at,
        )
        for item in row.occurrences.all()[:100]
    )
    return RuntimeErrorDetail(
        **asdict(_list_item(row)),
        safe_traceback=row.safe_traceback,
        safe_context=row.safe_context,
        safe_context_json=json.dumps(
            row.safe_context, ensure_ascii=False, sort_keys=True
        ),
        occurrences=occurrences,
    )
