from dataclasses import dataclass
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client

from apps.accounts.models import Account, LoginSession, RoleAssignment


@dataclass(frozen=True, slots=True)
class IdentityMatrix:
    user: Account
    owner: Account
    other_author: Account
    admin: Account
    clients: dict[str, Client]


def create_account(
    label: str,
    *,
    author: bool = False,
    administrator: bool = False,
) -> Account:
    account = Account.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author or administrator:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.AUTHOR,
        )
    if administrator:
        RoleAssignment.objects.create(
            account=account,
            role=RoleAssignment.Role.ADMINISTRATOR,
        )
    return account


def authenticated_client(account: Account, *, address: str) -> Client:
    token, _session = LoginSession.issue(
        account=account,
        remember=False,
        client_ip=address,
    )
    client = Client(REMOTE_ADDR=address)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


@pytest.fixture
def identities() -> IdentityMatrix:
    user = create_account("qa002-user")
    owner = create_account("qa002-owner", author=True)
    other = create_account("qa002-other", author=True)
    admin = create_account("qa002-admin", administrator=True)
    return IdentityMatrix(
        user=user,
        owner=owner,
        other_author=other,
        admin=admin,
        clients={
            "visitor": Client(REMOTE_ADDR="198.51.100.10"),
            "user": authenticated_client(user, address="198.51.100.11"),
            "owner": authenticated_client(owner, address="198.51.100.12"),
            "other_author": authenticated_client(other, address="198.51.100.13"),
            "admin": authenticated_client(admin, address="198.51.100.14"),
        },
    )
