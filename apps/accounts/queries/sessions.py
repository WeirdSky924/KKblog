from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.utils import timezone

from apps.accounts.models import LoginSession
from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY
from apps.core.pagination import PageSlice


@dataclass(frozen=True, slots=True)
class SessionListItem:
    id: UUID
    browser_device: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    masked_ip: str
    is_current: bool
    remembered: bool


def session_list(
    *,
    account_id: UUID,
    current_session_id: UUID,
    now=None,
    page: int | None = None,
    page_size: int = 20,
) -> list[SessionListItem] | PageSlice[SessionListItem]:
    current_time = now or timezone.now()
    rows = LoginSession.objects.filter(
        account_id=account_id,
        revoked_at__isnull=True,
        expires_at__gt=current_time,
    ).order_by("-last_seen_at", "-created_at", "-id")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid session page")

    def item(row: LoginSession) -> SessionListItem:
        return SessionListItem(
            id=row.id,
            browser_device=row.user_agent_summary or "未知浏览器 · 未知设备",
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            masked_ip=DEFAULT_REDACTION_POLICY.mask_ip(row.created_ip),
            is_current=row.id == current_session_id,
            remembered=row.kind == LoginSession.Kind.REMEMBER_30D,
        )

    if page is None:
        return [item(row) for row in rows]
    paginator = Paginator(rows, page_size)
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
