from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.accounts.models import Account


@dataclass(frozen=True, slots=True)
class PublicAccountIdentity:
    account_id: UUID
    display_name: str
    avatar_url: str | None
    avatar_initial: str
    profile_url: str


class PublicAccountNotFound(LookupError):
    pass


def public_account_identity(account_id) -> PublicAccountIdentity:
    try:
        account = Account.objects.only(
            "id", "email", "nickname", "avatar_asset_id", "status"
        ).get(pk=account_id, status=Account.Status.ACTIVE)
    except (Account.DoesNotExist, ValidationError, ValueError, TypeError):
        raise PublicAccountNotFound("Public account profile does not exist") from None
    display_name = account.nickname or account.email.partition("@")[0]
    return PublicAccountIdentity(
        account_id=account.id,
        display_name=display_name,
        avatar_url=(
            f"/_kaj/media/{account.avatar_asset_id}"
            if account.avatar_asset_id
            else None
        ),
        avatar_initial=display_name[0] if display_name else "?",
        profile_url=f"/people/{account.id}/",
    )
