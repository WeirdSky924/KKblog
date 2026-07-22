from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import Account, BootstrapState, RoleAssignment


class BootstrapError(RuntimeError):
    pass


def _validate_initial_password(value: str) -> None:
    classes = (
        any(char.islower() for char in value),
        any(char.isupper() for char in value),
        any(char.isdigit() for char in value),
        any(not char.isalnum() for char in value),
    )
    if len(value) < 16 or sum(classes) < 3:
        raise BootstrapError("初始管理员密钥不符合强度要求")


def _lock_bootstrap() -> None:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ["kaj.initial-administrator"],
            )


def bootstrap_administrator(
    *, email: str, initial_password: str, production: bool
) -> Account:
    if production and (not email or email.casefold().endswith("@kaj.test")):
        raise BootstrapError("生产管理员邮箱缺失或无效")
    _validate_initial_password(initial_password)
    with transaction.atomic():
        _lock_bootstrap()
        state, _ = BootstrapState.objects.select_for_update().get_or_create(
            key="initial-administrator"
        )
        if (
            state.consumed_at
            or RoleAssignment.objects.filter(
                role=RoleAssignment.Role.ADMINISTRATOR
            ).exists()
        ):
            raise BootstrapError("管理员初始化密钥已失效")
        try:
            account = Account.objects.create_account(
                email=email,
                password=initial_password,
                must_change_password=True,
            )
        except ValidationError as exc:
            raise BootstrapError("管理员身份无效") from exc
        RoleAssignment.objects.bulk_create(
            [
                RoleAssignment(account=account, role=RoleAssignment.Role.AUTHOR),
                RoleAssignment(account=account, role=RoleAssignment.Role.ADMINISTRATOR),
            ]
        )
        state.consumed_at = timezone.now()
        state.account_id = account.id
        state.save(update_fields=["consumed_at", "account_id"])
        return account
