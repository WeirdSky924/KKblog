from uuid import UUID

from apps.accounts.deletion import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
    configure_account_deletion_cleanup,
)
from apps.accounts.email_templates import (
    DEFAULT_VERIFICATION_EMAIL_TEMPLATE,
    MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES,
    EmailTemplateError,
    VerificationEmailConfiguration,
    render_verification_email_html,
    validate_verification_email_template,
)
from apps.accounts.models import Account, RoleAssignment
from apps.accounts.queries.administration import (
    ADMIN_ACCOUNT_STATUSES,
    AccountAdministrationQueryError,
    AdminAccountItem,
    AdminAccountPage,
    AdminAuthorChoice,
    admin_account_detail,
    admin_account_page,
    admin_author_choices,
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
    PublicAuthorSearchPage,
    public_account_identities,
    public_account_identity,
    search_public_author_page,
    search_public_authors,
)
from apps.accounts.queries.security_events import (
    security_event_detail,
    security_event_list,
)
from apps.accounts.services.article_explanation_preferences import (
    ArticleExplanationPreferenceError,
    ArticleExplanationPreferences,
    article_explanation_preferences,
    change_article_explanation_preferences,
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
    AttachmentCapabilityState,
    delete_account,
    set_account_enabled,
    set_attachment_upload_capability,
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


def can_upload_attachments(account_id: UUID | str | None) -> bool:
    if account_id is None:
        return False
    return Account.objects.filter(
        pk=account_id,
        status=Account.Status.ACTIVE,
        attachment_upload_enabled=True,
        roles__role=RoleAssignment.Role.AUTHOR,
    ).exists()


def is_active_account(account_id: UUID | str | None) -> bool:
    if account_id is None:
        return False
    return Account.objects.filter(pk=account_id, status=Account.Status.ACTIVE).exists()


def lock_active_account(account_id: UUID | str | None) -> bool:
    if account_id is None:
        return False
    return (
        Account.objects.select_for_update()
        .filter(
            pk=account_id,
            status=Account.Status.ACTIVE,
        )
        .first()
        is not None
    )


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
    "AdminAuthorChoice",
    "InviteDetail",
    "InviteError",
    "InviteListItem",
    "IssuedInvite",
    "admin_account_detail",
    "admin_account_page",
    "admin_author_choices",
    "block_ip",
    "can_upload_attachments",
    "active_administrator_id",
    "AccountDeletionDisposition",
    "configure_account_deletion_cleanup",
    "AccountLifecycleError",
    "AttachmentCapabilityState",
    "AuthorPreferenceError",
    "AuthorPreferences",
    "ArticleExplanationPreferenceError",
    "ArticleExplanationPreferences",
    "AuthorArticleDecision",
    "DEFAULT_VERIFICATION_EMAIL_TEMPLATE",
    "EmailTemplateError",
    "MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES",
    "PublicAccountIdentity",
    "PublicAccountNotFound",
    "PublicAuthorSearchPage",
    "RestrictionError",
    "VerificationEmailConfiguration",
    "clear_account_restrictions",
    "clear_ip_send_restriction",
    "default_restriction_store",
    "author_preferences",
    "change_author_preferences",
    "article_explanation_preferences",
    "change_article_explanation_preferences",
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
    "lock_active_account",
    "public_account_identities",
    "public_account_identity",
    "search_public_author_page",
    "search_public_authors",
    "security_event_detail",
    "security_event_list",
    "set_account_enabled",
    "set_attachment_upload_capability",
    "set_author_role",
    "revoke_invites",
    "render_verification_email_html",
    "unblock_ip",
    "validate_verification_email_template",
]
