from uuid import UUID

from apps.accounts.deletion import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
)
from apps.accounts.models import Account, RoleAssignment
from apps.accounts.queries.administration import (
    ADMIN_ACCOUNT_STATUSES,
    AccountAdministrationQueryError,
    AdminAccountItem,
    AdminAccountPage,
    admin_account_detail,
    admin_account_page,
)
from apps.accounts.queries.invites import (
    InviteDetail,
    InviteListItem,
    invite_detail,
    invite_list,
)
from apps.accounts.queries.ip_blocks import (
    ip_block_detail,
    ip_block_list,
    is_ip_blocked,
)
from apps.accounts.queries.profile import (
    PublicAccountIdentity,
    PublicAccountNotFound,
    public_account_identities,
    public_account_identity,
)
from apps.accounts.queries.security_events import (
    security_event_detail,
    security_event_list,
)
from apps.accounts.services.author_preferences import (
    AuthorPreferenceError,
    AuthorPreferences,
    author_preferences,
    change_author_preferences,
)
from apps.accounts.services.invites import (
    InviteError,
    IssuedInvite,
    generate_invite_codes,
    revoke_invites,
)
from apps.accounts.services.ip_blocks import block_ip, unblock_ip
from apps.accounts.services.lifecycle import (
    AccountLifecycleError,
    delete_account,
    set_account_enabled,
    set_author_role,
)
from apps.accounts.services.restrictions import (
    RestrictionError,
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


def is_active_author(account_id: UUID | str | None) -> bool:
    if account_id is None:
        return False
    return RoleAssignment.objects.filter(
        account_id=account_id,
        role=RoleAssignment.Role.AUTHOR,
        account__status=Account.Status.ACTIVE,
    ).exists()


def is_active_account(account_id: UUID | str | None) -> bool:
    if account_id is None:
        return False
    return Account.objects.filter(pk=account_id, status=Account.Status.ACTIVE).exists()


def active_administrator_id() -> UUID | None:
    return (
        RoleAssignment.objects.filter(
            role=RoleAssignment.Role.ADMINISTRATOR,
            account__status=Account.Status.ACTIVE,
        )
        .values_list("account_id", flat=True)
        .first()
    )


__all__ = [
    "ADMIN_ACCOUNT_STATUSES",
    "AccountAdministrationQueryError",
    "AdminAccountItem",
    "AdminAccountPage",
    "InviteDetail",
    "InviteError",
    "InviteListItem",
    "IssuedInvite",
    "admin_account_detail",
    "admin_account_page",
    "block_ip",
    "active_administrator_id",
    "AccountDeletionDisposition",
    "AccountLifecycleError",
    "AuthorPreferenceError",
    "AuthorPreferences",
    "AuthorArticleDecision",
    "PublicAccountIdentity",
    "PublicAccountNotFound",
    "RestrictionError",
    "clear_account_restrictions",
    "clear_ip_send_restriction",
    "default_restriction_store",
    "author_preferences",
    "change_author_preferences",
    "delete_account",
    "generate_invite_codes",
    "invite_detail",
    "invite_list",
    "ip_block_detail",
    "ip_block_list",
    "is_ip_blocked",
    "is_administrator",
    "is_active_author",
    "is_active_account",
    "public_account_identities",
    "public_account_identity",
    "security_event_detail",
    "security_event_list",
    "set_account_enabled",
    "set_author_role",
    "revoke_invites",
    "unblock_ip",
]
