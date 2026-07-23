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
_provider: ProfileIdentityProvider | None = None


def configure_profile_identity_provider(provider: ProfileIdentityProvider) -> None:
    global _provider
    if not callable(provider):
        raise TypeError("profile identity provider must be callable")
    _provider = provider


def resolve_profile_identity(account_id: UUID) -> ProfileIdentity | None:
    if _provider is None:
        raise RuntimeError("Profile identity provider is not configured")
    return _provider(account_id)
