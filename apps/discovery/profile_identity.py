from collections.abc import Callable
from typing import Protocol
from uuid import UUID


class ProfileIdentity(Protocol):
    account_id: UUID
    display_name: str
    avatar_url: str | None
    avatar_initial: str
    profile_url: str


ProfileIdentityProvider = Callable[[UUID], ProfileIdentity | None]
ProfileIdentityCollectionProvider = Callable[
    [tuple[UUID, ...]], tuple[ProfileIdentity, ...]
]
ProfileIdentitySuggestionProvider = Callable[..., tuple[ProfileIdentity, ...]]


class ProfileIdentitySearchPage(Protocol):
    items: tuple[ProfileIdentity, ...]
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool


ProfileIdentityPageProvider = Callable[..., ProfileIdentitySearchPage]
_provider: ProfileIdentityProvider | None = None
_collection_provider: ProfileIdentityCollectionProvider | None = None
_suggestion_provider: ProfileIdentitySuggestionProvider | None = None
_page_provider: ProfileIdentityPageProvider | None = None


def configure_profile_identity_provider(provider: ProfileIdentityProvider) -> None:
    global _provider
    if not callable(provider):
        raise TypeError("profile identity provider must be callable")
    _provider = provider


def configure_profile_identity_collection_provider(
    provider: ProfileIdentityCollectionProvider,
) -> None:
    global _collection_provider
    if not callable(provider):
        raise TypeError("Profile identity collection provider must be callable")
    _collection_provider = provider


def configure_profile_identity_search_providers(
    *,
    suggestions: ProfileIdentitySuggestionProvider,
    page: ProfileIdentityPageProvider,
) -> None:
    global _suggestion_provider, _page_provider
    if not callable(suggestions) or not callable(page):
        raise TypeError("Profile identity search providers must be callable")
    _suggestion_provider = suggestions
    _page_provider = page


def resolve_profile_identity(account_id: UUID) -> ProfileIdentity | None:
    if _provider is None:
        raise RuntimeError("Profile identity provider is not configured")
    return _provider(account_id)


def resolve_profile_identities(
    account_ids: tuple[UUID, ...],
) -> dict[UUID, ProfileIdentity]:
    identities = tuple(dict.fromkeys(account_ids))
    if len(identities) > 1000 or any(
        not isinstance(account_id, UUID) for account_id in identities
    ):
        raise ValueError("account_ids must contain at most 1000 UUID values")
    if not identities:
        return {}
    if _collection_provider is None:
        if _provider is None:
            raise RuntimeError("Profile identity provider is not configured")
        return {
            account_id: identity
            for account_id in identities
            if (identity := _provider(account_id)) is not None
        }
    return {
        identity.account_id: identity for identity in _collection_provider(identities)
    }


def search_profile_identities(
    *, query: str, limit: int = 5
) -> tuple[ProfileIdentity, ...]:
    if _suggestion_provider is None:
        raise RuntimeError("Profile identity search provider is not configured")
    return _suggestion_provider(query=query, limit=limit)


def search_profile_identity_page(
    *, query: str, page: int = 1, page_size: int = 20
) -> ProfileIdentitySearchPage:
    if _page_provider is None:
        raise RuntimeError("Profile identity page provider is not configured")
    return _page_provider(query=query, page=page, page_size=page_size)
