from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.accounts.models import InviteCode


@dataclass(frozen=True, slots=True)
class InviteListItem:
    id: str
    display_suffix: str
    state: str
    expires_at: datetime
    redeemed_by_id: str | None
    created_at: datetime


def invite_list(*, state: str = "", now=None, limit: int = 200) -> list[InviteListItem]:
    if not 1 <= limit <= 1000:
        raise ValueError("Invalid invite query limit")
    current = now or timezone.now()
    queryset = InviteCode.objects.all()
    if state == "ACTIVE":
        queryset = queryset.filter(
            redeemed_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=current,
        )
    elif state == "USED":
        queryset = queryset.filter(redeemed_at__isnull=False)
    elif state == "REVOKED":
        queryset = queryset.filter(redeemed_at__isnull=True, revoked_at__isnull=False)
    elif state == "EXPIRED":
        queryset = queryset.filter(
            redeemed_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__lte=current,
        )
    elif state:
        raise ValueError("Invalid invite state")
    queryset = queryset.order_by("-created_at", "-id")[:limit]
    return [
        InviteListItem(
            id=str(invite.id),
            display_suffix=invite.display_suffix,
            state=invite.state(now=current),
            expires_at=invite.expires_at,
            redeemed_by_id=(
                str(invite.redeemed_by_id) if invite.redeemed_by_id else None
            ),
            created_at=invite.created_at,
        )
        for invite in queryset
    ]
