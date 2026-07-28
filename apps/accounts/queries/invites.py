from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import InviteCode
from apps.accounts.queries.administration import (
    AccountAdministrationQueryError,
    AdminAccountItem,
    admin_account_detail,
)


@dataclass(frozen=True, slots=True)
class InviteListItem:
    id: str
    display_suffix: str
    state: str
    expires_at: datetime
    redeemed_by_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InviteDetail:
    id: str
    display_suffix: str
    state: str
    expires_at: datetime
    created_at: datetime
    redeemed_at: datetime | None
    redeemed_account: AdminAccountItem | None


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


def invite_detail(*, invite_id, actor_id, now=None) -> InviteDetail:
    # Reuse the administrator account query as the owner-level permission check.
    admin_account_detail(actor_id=actor_id, account_id=actor_id)
    try:
        invite = InviteCode.objects.get(pk=invite_id)
    except (InviteCode.DoesNotExist, ValidationError):
        raise AccountAdministrationQueryError("邀请码不存在") from None
    redeemed_account = None
    if invite.redeemed_by_id is not None:
        redeemed_account = admin_account_detail(
            actor_id=actor_id,
            account_id=invite.redeemed_by_id,
        )
    return InviteDetail(
        id=str(invite.id),
        display_suffix=invite.display_suffix,
        state=invite.state(now=now or timezone.now()),
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        redeemed_at=invite.redeemed_at,
        redeemed_account=redeemed_account,
    )


__all__ = ["InviteDetail", "InviteListItem", "invite_detail", "invite_list"]
