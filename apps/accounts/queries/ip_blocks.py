from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q

from apps.accounts.models import IpBlock
from apps.accounts.network import ClientIpError, network_subject_digest, normalize_ip
from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY


@dataclass(frozen=True, slots=True)
class IpBlockListItem:
    id: str
    masked_address: str
    address_digest: str
    note: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IpBlockDetail:
    id: str
    address: str
    note: str
    created_at: datetime
    unblocked_at: datetime | None


def _require_administrator(is_admin: bool) -> None:
    if not is_admin:
        raise PermissionError("IP blocks require administrator access")


def ip_block_list(
    *, is_admin: bool, keyword: str = "", limit: int = 200
) -> list[IpBlockListItem]:
    _require_administrator(is_admin)
    if not 1 <= limit <= 500:
        raise ValueError("Invalid IP block limit")
    term = keyword.strip()
    rows = IpBlock.objects.filter(unblocked_at__isnull=True)
    if term:
        query = Q(note__icontains=term)
        try:
            query |= Q(address=normalize_ip(term))
        except ClientIpError:
            pass
        rows = rows.filter(query)
    return [
        IpBlockListItem(
            id=row.id,
            masked_address=DEFAULT_REDACTION_POLICY.mask_ip(row.address),
            address_digest=network_subject_digest(row.address),
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows.order_by("-created_at", "-id")[:limit]
    ]


def ip_block_detail(*, block_id: str, is_admin: bool) -> IpBlockDetail:
    _require_administrator(is_admin)
    row = IpBlock.objects.get(pk=block_id)
    return IpBlockDetail(
        id=row.id,
        address=row.address,
        note=row.note,
        created_at=row.created_at,
        unblocked_at=row.unblocked_at,
    )
