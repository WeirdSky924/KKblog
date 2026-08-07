from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When

from apps.accounts.models import Account, RoleAssignment

_PUBLIC_AUTHOR_PAGE_SIZES = frozenset({10, 20, 50})


@dataclass(frozen=True, slots=True)
class PublicAccountIdentity:
    account_id: UUID
    display_name: str
    avatar_url: str | None
    avatar_initial: str
    profile_url: str


@dataclass(frozen=True, slots=True)
class PublicAuthorSearchPage:
    items: tuple[PublicAccountIdentity, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool


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


def _public_author_query(query: str):
    if not isinstance(query, str):
        raise ValueError("query is required")
    normalized = unicodedata.normalize("NFKC", query).strip()
    if not normalized or len(normalized) > 100:
        raise ValueError("query must contain between 1 and 100 characters")
    return (
        Account.objects.only(
            "id",
            "email",
            "nickname",
            "normalized_nickname",
            "avatar_asset_id",
            "status",
        )
        .filter(
            Q(nickname__icontains=normalized) | Q(email__istartswith=normalized),
            status=Account.Status.ACTIVE,
            roles__role=RoleAssignment.Role.AUTHOR,
        )
        .annotate(
            search_rank=Case(
                When(nickname__iexact=normalized, then=Value(0)),
                When(nickname__istartswith=normalized, then=Value(1)),
                When(email__istartswith=normalized, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .distinct()
        .order_by("search_rank", "normalized_nickname", "email", "id")
    )


def search_public_authors(
    *, query: str, limit: int = 5
) -> tuple[PublicAccountIdentity, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("limit must be between 1 and 5")
    return tuple(
        _public_identity(account) for account in _public_author_query(query)[:limit]
    )


def search_public_author_page(
    *, query: str, page: int = 1, page_size: int = 20
) -> PublicAuthorSearchPage:
    if isinstance(page_size, bool) or page_size not in _PUBLIC_AUTHOR_PAGE_SIZES:
        raise ValueError("page size must be 10, 20, or 50")
    try:
        page_number = max(1, int(page)) if not isinstance(page, bool) else 1
    except (TypeError, ValueError):
        page_number = 1
    paginator = Paginator(_public_author_query(query), page_size)
    active_page = paginator.get_page(page_number)
    return PublicAuthorSearchPage(
        items=tuple(_public_identity(account) for account in active_page.object_list),
        page_number=active_page.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=active_page.has_previous(),
        has_next=active_page.has_next(),
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
