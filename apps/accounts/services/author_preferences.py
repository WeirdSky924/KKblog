from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.accounts.models import Account, RoleAssignment


class AuthorPreferenceError(ValueError):
    def __init__(self, message: str = "作者偏好不可用。") -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AuthorPreferences:
    auto_republish_enabled: bool


def _identity(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise AuthorPreferenceError from None


def _active_author(account_id: UUID, *, for_update: bool = False):
    accounts = Account.objects.select_for_update() if for_update else Account.objects
    try:
        return accounts.get(
            pk=account_id,
            status=Account.Status.ACTIVE,
            roles__role=RoleAssignment.Role.AUTHOR,
        )
    except Account.DoesNotExist:
        raise AuthorPreferenceError from None


def author_preferences(*, account_id) -> AuthorPreferences:
    account = _active_author(_identity(account_id))
    return AuthorPreferences(account.auto_republish_enabled)


def change_author_preferences(
    *,
    account_id,
    auto_republish_enabled: bool,
    client_ip: str,
    trace_code: str,
    audit_writer,
) -> AuthorPreferences:
    if type(auto_republish_enabled) is not bool:
        raise AuthorPreferenceError("请选择有效的自动发布偏好。")
    if not callable(audit_writer):
        raise TypeError("audit_writer must be callable")
    identity = _identity(account_id)
    with transaction.atomic():
        account = _active_author(identity, for_update=True)
        before = {"auto_republish_enabled": account.auto_republish_enabled}
        if account.auto_republish_enabled == auto_republish_enabled:
            return AuthorPreferences(account.auto_republish_enabled)
        account.auto_republish_enabled = auto_republish_enabled
        account.save(update_fields=("auto_republish_enabled", "updated_at"))
        audit_writer(
            action="accounts.author_preference.change",
            actor_id=account.id,
            target_id=str(account.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after={"auto_republish_enabled": account.auto_republish_enabled},
            summary="Change own author preferences",
        )
    return AuthorPreferences(account.auto_republish_enabled)


__all__ = [
    "AuthorPreferenceError",
    "AuthorPreferences",
    "author_preferences",
    "change_author_preferences",
]
