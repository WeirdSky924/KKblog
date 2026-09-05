from dataclasses import dataclass
from datetime import datetime

from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.models import IpBlock
from apps.accounts.network import ClientIpError, network_subject_digest, normalize_ip
from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY
from apps.core.pagination import PageSlice


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


def is_ip_blocked(address: str) -> bool:
    try:
        normalized = normalize_ip(address)
    except ClientIpError:
        return True
    return IpBlock.objects.filter(
        address=normalized,
        unblocked_at__isnull=True,
    ).exists()


def _require_administrator(is_admin: bool) -> None:
    if not is_admin:
        raise PermissionError("IP blocks require administrator access")


def ip_block_list(
    *,
    is_admin: bool,
    keyword: str = "",
    limit: int = 200,
    page: int | None = None,
    page_size: int = 20,
) -> list[IpBlockListItem] | PageSlice[IpBlockListItem]:
    _require_administrator(is_admin)
    if not 1 <= limit <= 500:
        raise ValueError("Invalid IP block limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid IP block page")
    term = keyword.strip()
    rows = IpBlock.objects.filter(unblocked_at__isnull=True)
    if term:
        query = Q(note__icontains=term)
        try:
            query |= Q(address=normalize_ip(term))
        except ClientIpError:
            pass
        rows = rows.filter(query)
    ordered = rows.order_by("-created_at", "-id")

    def item(row):
        return IpBlockListItem(
            id=row.id,
            masked_address=DEFAULT_REDACTION_POLICY.mask_ip(row.address),
            address_digest=network_subject_digest(row.address),
            note=row.note,
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
