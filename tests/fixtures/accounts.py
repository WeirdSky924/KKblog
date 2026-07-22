from uuid import UUID

from apps.accounts.models import Account
from apps.accounts.services.bootstrap import bootstrap_administrator


def bootstrap_test_administrator() -> Account:
    return bootstrap_administrator(
        email="admin@kaj.test",
        initial_password="Strong-Initial-Password-411!",
        production=False,
    )


def create_test_account(
    *, email: str, password: str = "Valid-password-1", nickname: str | None = None
) -> Account:
    return Account.objects.create_account(
        email=email,
        password=password,
        nickname=nickname,
    )


def account_exists_for_test(account_id: UUID) -> bool:
    return Account.objects.filter(pk=account_id).exists()


def delete_test_account(account_id: UUID) -> None:
    Account.objects.get(pk=account_id).delete()
