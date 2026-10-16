from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.accounts.events import AUTHOR_PERMISSION_REQUESTED
from apps.accounts.models import Account, RoleAssignment
from apps.core.events import enqueue_event
from apps.core.time.clock import Clock, SystemClock


class AuthorPermissionRequestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AuthorPermissionRequestResult:
    created: bool
    is_author: bool


def submit_author_permission_request(
    *, account_id: UUID | str, trace_code: str, clock: Clock | None = None
) -> AuthorPermissionRequestResult:
    try:
        identity = UUID(str(account_id))
    except (TypeError, ValueError):
        raise AuthorPermissionRequestError("账户状态无效") from None

    active_clock = clock or SystemClock()
    with transaction.atomic():
        account = (
            Account.objects.select_for_update()
            .filter(pk=identity, status=Account.Status.ACTIVE)
            .first()
        )
        if account is None:
            raise AuthorPermissionRequestError("账户状态无效")
        if account.roles.filter(role=RoleAssignment.Role.AUTHOR).exists():
            return AuthorPermissionRequestResult(created=False, is_author=True)
        if account.author_permission_requested_at is not None:
            return AuthorPermissionRequestResult(created=False, is_author=False)

        account.author_permission_requested_at = active_clock.now()
        account.save(update_fields=("author_permission_requested_at", "updated_at"))
        enqueue_event(
            AUTHOR_PERMISSION_REQUESTED,
            aggregate_type="account",
            aggregate_id=str(account.id),
            actor_id=account.id,
            trace_code=trace_code,
            payload={},
            clock=active_clock,
        )
        return AuthorPermissionRequestResult(created=True, is_author=False)


__all__ = [
    "AuthorPermissionRequestError",
    "AuthorPermissionRequestResult",
    "submit_author_permission_request",
]
