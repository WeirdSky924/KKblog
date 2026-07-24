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
    return _public_identity(account)


def _public_identity(account: Account) -> PublicAccountIdentity:
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


def public_account_identities(
    account_ids: tuple[UUID, ...],
) -> tuple[PublicAccountIdentity, ...]:
    if not isinstance(account_ids, tuple) or len(account_ids) > 1000:
        raise ValueError("account_ids must be a tuple of at most 1000 IDs")
    if any(not isinstance(account_id, UUID) for account_id in account_ids):
        raise ValueError("account_ids must contain UUID values")
    identities = set(account_ids)
    if not identities:
        return ()
    accounts = Account.objects.only(
        "id",
        "email",
        "nickname",
        "avatar_asset_id",
        "status",
    ).filter(pk__in=identities, status=Account.Status.ACTIVE)
    return tuple(_public_identity(account) for account in accounts)
