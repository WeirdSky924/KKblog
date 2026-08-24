from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.deletion import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
    run_account_deletion_cleanup,
)
from apps.accounts.events import (
    ACCOUNT_DELETED,
    ACCOUNT_DISABLED,
    ACCOUNT_ENABLED,
    AUTHOR_ROLE_CHANGED,
)
from apps.accounts.models import (
    Account,
    AccountDeletion,
    LoginSession,
    RoleAssignment,
)
from apps.core.events import enqueue_event
from apps.media.public import release_owner_assets

AuditWriter = Callable[..., object]
DispositionVerifier = Callable[[AccountDeletionDisposition], bool]


class AccountLifecycleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AuthorRoleState:
    account_id: UUID
    enabled: bool
    changed: bool


@dataclass(frozen=True, slots=True)
class AccountStatusState:
    account_id: UUID
    status: str
    changed: bool
    revoked_sessions: int


@dataclass(frozen=True, slots=True)
class AttachmentCapabilityState:
    account_id: UUID
    enabled: bool
    changed: bool


def _identity(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise AccountLifecycleError("账户不存在") from None


def _lock_accounts(actor_id, account_id) -> tuple[Account, Account]:
    actor_key = _identity(actor_id)
    account_key = _identity(account_id)
    rows = {
        row.id: row
        for row in Account.objects.select_for_update()
        .filter(pk__in={actor_key, account_key})
        .order_by("id")
    }
    actor = rows.get(actor_key)
    target = rows.get(account_key)
    if actor is None or target is None:
        raise AccountLifecycleError("账户不存在")
    if (
        actor.status != Account.Status.ACTIVE
        or not RoleAssignment.objects.filter(
            account=actor, role=RoleAssignment.Role.ADMINISTRATOR
        ).exists()
    ):
        raise PermissionError("Administrator access required")
    return actor, target


def _roles(account: Account) -> list[str]:
    return list(account.roles.order_by("role").values_list("role", flat=True))


def _protect_administrator(actor: Account, target: Account) -> None:
    if (
        actor.id == target.id
        or target.roles.filter(role=RoleAssignment.Role.ADMINISTRATOR).exists()
    ):
        raise AccountLifecycleError("管理员账户不能执行该操作")


def _require_writer(audit_writer: AuditWriter) -> None:
    if not callable(audit_writer):
        raise TypeError("audit_writer must be callable")


def set_author_role(
    *,
    actor_id,
    account_id,
    enabled: bool,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
) -> AuthorRoleState:
    _require_writer(audit_writer)
    if not isinstance(enabled, bool):
        raise AccountLifecycleError("作者角色状态无效")
    with transaction.atomic():
        actor, target = _lock_accounts(actor_id, account_id)
        is_administrator = target.roles.filter(
            role=RoleAssignment.Role.ADMINISTRATOR
        ).exists()
        if is_administrator and not enabled:
            raise AccountLifecycleError("管理员作者角色不能撤销")
        before_roles = _roles(target)
        currently_enabled = RoleAssignment.Role.AUTHOR in before_roles
        if currently_enabled == enabled:
            return AuthorRoleState(target.id, enabled, False)

        attachment_capability_revoked = False
        if enabled:
            RoleAssignment.objects.create(
                account=target,
                role=RoleAssignment.Role.AUTHOR,
                granted_by=actor,
            )
        else:
            assignment = RoleAssignment.objects.get(
                account=target, role=RoleAssignment.Role.AUTHOR
            )
            assignment.delete()
            if target.attachment_upload_enabled:
                target.attachment_upload_enabled = False
                target.save(update_fields=("attachment_upload_enabled", "updated_at"))
                attachment_capability_revoked = True
        after_roles = _roles(target)
        audit_writer(
            action="accounts.role.set",
            actor_id=actor.id,
            target_id=str(target.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"roles": before_roles, "status": target.status},
            after={"roles": after_roles, "status": target.status},
            summary="Set account author role",
        )
        if attachment_capability_revoked:
            audit_writer(
                action="accounts.attachment_capability.set",
                actor_id=actor.id,
                target_id=str(target.id),
                trace_code=trace_code,
                client_ip=client_ip,
                before={"attachment_upload_enabled": True},
                after={"attachment_upload_enabled": False},
                summary="Revoke attachment capability with author role",
            )
        enqueue_event(
            AUTHOR_ROLE_CHANGED,
            aggregate_type="account",
            aggregate_id=str(target.id),
            actor_id=actor.id,
            trace_code=trace_code,
            payload={"enabled": enabled},
        )
        return AuthorRoleState(target.id, enabled, True)


def set_attachment_upload_capability(
    *,
    actor_id,
    account_id,
    enabled: bool,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
) -> AttachmentCapabilityState:
    _require_writer(audit_writer)
    if not isinstance(enabled, bool):
        raise AccountLifecycleError("附件能力状态无效")
    with transaction.atomic():
        actor, target = _lock_accounts(actor_id, account_id)
        if not target.roles.filter(role=RoleAssignment.Role.AUTHOR).exists():
            raise AccountLifecycleError("只有作者账户可以授予附件能力")
        if target.attachment_upload_enabled == enabled:
            return AttachmentCapabilityState(target.id, enabled, False)
        before = {"attachment_upload_enabled": target.attachment_upload_enabled}
        target.attachment_upload_enabled = enabled
        target.save(update_fields=("attachment_upload_enabled", "updated_at"))
        audit_writer(
            action="accounts.attachment_capability.set",
            actor_id=actor.id,
            target_id=str(target.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after={"attachment_upload_enabled": enabled},
            summary="Set author attachment upload capability",
        )
        return AttachmentCapabilityState(target.id, enabled, True)


def set_account_enabled(
    *,
    actor_id,
    account_id,
    enabled: bool,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
) -> AccountStatusState:
    _require_writer(audit_writer)
    if not isinstance(enabled, bool):
        raise AccountLifecycleError("账户状态无效")
    with transaction.atomic():
        actor, target = _lock_accounts(actor_id, account_id)
        _protect_administrator(actor, target)
        desired = Account.Status.ACTIVE if enabled else Account.Status.DISABLED
        roles = _roles(target)
        if target.status == desired:
            return AccountStatusState(target.id, desired, False, 0)

        previous = target.status
        target.status = desired
        target.save(update_fields=("status", "updated_at"))
        revoked_sessions = 0
        if not enabled:
            now = timezone.now()
            revoked_sessions = LoginSession.objects.filter(
                account=target,
                revoked_at__isnull=True,
                expires_at__gt=now,
            ).update(revoked_at=now)
        audit_writer(
            action="accounts.account.status",
            actor_id=actor.id,
            target_id=str(target.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"status": previous, "roles": roles},
            after={"status": desired, "roles": roles},
            summary="Set account enabled state",
        )
        enqueue_event(
            ACCOUNT_ENABLED if enabled else ACCOUNT_DISABLED,
            aggregate_type="account",
            aggregate_id=str(target.id),
            actor_id=actor.id,
            trace_code=trace_code,
            payload={},
        )
        return AccountStatusState(target.id, desired, True, revoked_sessions)


def _deletion_disposition(
    *,
    target: Account,
    author_disposition: AccountDeletionDisposition,
    verify_author_disposition: DispositionVerifier,
) -> tuple[AuthorArticleDecision, str, int]:
    if (
        not isinstance(author_disposition, AccountDeletionDisposition)
        or author_disposition.account_id != target.id
        or not callable(verify_author_disposition)
    ):
        raise AccountLifecycleError("作者文章处置尚未完成")
    try:
        verified = verify_author_disposition(author_disposition)
    except Exception as exc:
        raise AccountLifecycleError("作者文章处置验证失败") from exc
    if verified is not True:
        raise AccountLifecycleError("作者文章处置尚未完成")
    return (
        author_disposition.decision,
        author_disposition.disposition_id,
        author_disposition.article_count,
    )


def delete_account(
    *,
    actor_id,
    account_id,
    author_disposition: AccountDeletionDisposition,
    verify_author_disposition: DispositionVerifier,
    client_ip: str,
    trace_code: str,
    audit_writer: AuditWriter,
) -> AccountDeletion:
    _require_writer(audit_writer)
    with transaction.atomic():
        actor, target = _lock_accounts(actor_id, account_id)
        _protect_administrator(actor, target)
        roles = _roles(target)
        was_author = RoleAssignment.Role.AUTHOR in roles
        decision, disposition_id, article_count = _deletion_disposition(
            target=target,
            author_disposition=author_disposition,
            verify_author_disposition=verify_author_disposition,
        )
        deletion = AccountDeletion.objects.create(
            account_id=target.id,
            was_author=was_author,
            author_disposition=decision,
            disposition_id=disposition_id,
            article_count=article_count,
            deleted_by_id=actor.id,
        )
        audit_writer(
            action="accounts.account.delete",
            actor_id=actor.id,
            target_id=str(target.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={"status": target.status, "roles": roles},
            after={
                "status": "DELETED",
                "roles": [],
                "deletion_id": deletion.id,
                "disposition": decision.value,
            },
            summary="Delete account",
        )
        enqueue_event(
            ACCOUNT_DELETED,
            aggregate_type="account",
            aggregate_id=str(target.id),
            actor_id=actor.id,
            trace_code=trace_code,
            payload={
                "deletion_id": deletion.id,
                "was_author": was_author,
                "author_disposition": decision.value,
                "disposition_id": disposition_id,
                "article_count": article_count,
            },
        )
        # Domain owners register their cleanup port during app initialization.
        # Accounts keeps the deletion transaction authoritative without importing
        # another domain's private models or services.
        run_account_deletion_cleanup(target.id)
        release_owner_assets(owner_id=target.id)
        target.delete()
        return deletion
