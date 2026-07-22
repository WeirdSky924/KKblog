from uuid import UUID

from apps.accounts.deletion import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
)
from apps.accounts.models import RoleAssignment
from apps.accounts.queries.ip_blocks import ip_block_detail, ip_block_list
from apps.accounts.queries.security_events import (
    security_event_detail,
    security_event_list,
)
from apps.accounts.services.ip_blocks import block_ip, unblock_ip
from apps.accounts.services.lifecycle import (
    AccountLifecycleError,
    delete_account,
    set_account_enabled,
    set_author_role,
)
from apps.accounts.services.restrictions import (
    clear_account_restrictions,
    clear_ip_send_restriction,
    default_restriction_store,
)


def is_administrator(account_id: UUID | str | None) -> bool:
    if account_id is None:
        return False
    return RoleAssignment.objects.filter(
        account_id=account_id,
        role=RoleAssignment.Role.ADMINISTRATOR,
        account__status="ACTIVE",
    ).exists()


__all__ = [
    "block_ip",
    "AccountDeletionDisposition",
    "AccountLifecycleError",
    "AuthorArticleDecision",
    "clear_account_restrictions",
    "clear_ip_send_restriction",
    "default_restriction_store",
    "delete_account",
    "ip_block_detail",
    "ip_block_list",
    "is_administrator",
    "security_event_detail",
    "security_event_list",
    "set_account_enabled",
    "set_author_role",
    "unblock_ip",
]
