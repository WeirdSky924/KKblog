from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from apps.accounts.models import LoginSession
from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY


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
    *, account_id: UUID, current_session_id: UUID, now=None
) -> list[SessionListItem]:
    current_time = now or timezone.now()
    rows = LoginSession.objects.filter(
        account_id=account_id,
        revoked_at__isnull=True,
        expires_at__gt=current_time,
    ).order_by("-last_seen_at", "-created_at", "-id")
    return [
        SessionListItem(
            id=row.id,
            browser_device=row.user_agent_summary or "未知浏览器 · 未知设备",
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            masked_ip=DEFAULT_REDACTION_POLICY.mask_ip(row.created_ip),
            is_current=row.id == current_session_id,
            remembered=row.kind == LoginSession.Kind.REMEMBER_30D,
        )
        for row in rows
    ]
