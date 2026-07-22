from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from apps.accounts.models import SecurityEvent
from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY


@dataclass(frozen=True, slots=True)
class SecurityEventListItem:
    id: str
    event_type: str
    account_id: UUID | None
    masked_ip: str
    trace_code: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SecurityEventDetail:
    id: str
    event_type: str
    account_id: UUID | None
    client_ip: str
    trace_code: str
    safe_summary: MappingProxyType
    created_at: datetime


def _require_administrator(is_admin: bool) -> None:
    if not is_admin:
        raise PermissionError("Security events require administrator access")


def security_event_list(
    *, is_admin: bool, limit: int = 50
) -> list[SecurityEventListItem]:
    _require_administrator(is_admin)
    if not 1 <= limit <= 200:
        raise ValueError("Invalid security event limit")
    rows = SecurityEvent.objects.order_by("-created_at", "-id")[:limit]
    return [
        SecurityEventListItem(
            id=row.id,
            event_type=row.event_type,
            account_id=row.account_id,
            masked_ip=DEFAULT_REDACTION_POLICY.mask_ip(row.client_ip),
            trace_code=row.trace_code,
            created_at=row.created_at,
        )
        for row in rows
    ]


def security_event_detail(*, event_id: str, is_admin: bool) -> SecurityEventDetail:
    _require_administrator(is_admin)
    row = SecurityEvent.objects.get(pk=event_id)
    return SecurityEventDetail(
        id=row.id,
        event_type=row.event_type,
        account_id=row.account_id,
        client_ip=row.client_ip,
        trace_code=row.trace_code,
        safe_summary=MappingProxyType(dict(row.safe_summary)),
        created_at=row.created_at,
    )
