import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import formataddr
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import ProgrammingError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.accounts.email_templates import verification_email_sender_name
from apps.accounts.models import (
    Account,
    AdminPasswordReset,
    LoginSession,
    RoleAssignment,
    SecurityEvent,
)
from apps.accounts.services.credentials import validate_password_strength

RESET_TOKEN_TTL = timedelta(minutes=30)
_TOKEN_PATTERN = re.compile(r"[0-9a-fA-F-]{36}\.[A-Za-z0-9_-]{32,128}\Z")


class AdminPasswordResetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IssuedAdminPasswordReset:
    expires_at: datetime


def _token_digest(raw_token: str, *, password_hash: str, email: str) -> str:
    scoped_token = (
        f"admin-password-reset:v1:{raw_token}:{password_hash}:{email}".encode()
    )
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), scoped_token, hashlib.sha256
    ).hexdigest()


def _active_administrator_exists(account_id) -> bool:
    return RoleAssignment.objects.filter(
        account_id=account_id,
        role=RoleAssignment.Role.ADMINISTRATOR,
        account__status=Account.Status.ACTIVE,
    ).exists()


def _send_reset_email(*, recipient: str, site_name: str, reset_url: str) -> None:
    sender_name = verification_email_sender_name(site_name)
    context = {
        "site_name": sender_name,
        "reset_url": reset_url,
        "minutes": int(RESET_TOKEN_TTL.total_seconds() // 60),
    }
    message = EmailMultiAlternatives(
        subject=f"{sender_name} · 密码重置",
        body=render_to_string("accounts/email/admin_password_reset.txt", context),
        from_email=formataddr((sender_name, settings.DEFAULT_FROM_EMAIL)),
        to=[recipient],
    )
    message.attach_alternative(
        render_to_string("accounts/email/admin_password_reset.html", context),
        "text/html",
    )
    if message.send(fail_silently=False) != 1:
        raise AdminPasswordResetError("重置邮件发送失败，请稍后重试。")


def issue_admin_password_reset_link(
    *,
    actor_id,
    account_id,
    client_ip: str,
    trace_code: str,
    audit_writer: Callable[..., object],
) -> IssuedAdminPasswordReset:
    now = timezone.now()
    expires_at = now + RESET_TOKEN_TTL
    with transaction.atomic():
        actor = Account.objects.select_for_update().filter(pk=actor_id).first()
        if (
            actor is None
            or actor.status != Account.Status.ACTIVE
            or not _active_administrator_exists(actor_id)
        ):
            raise PermissionError("只有启用的管理员可以发送密码重置邮件。")
        account = Account.objects.select_for_update().filter(pk=account_id).first()
        if account is None:
            raise AdminPasswordResetError("账户不存在或已删除。")
        raw_token = f"{account.pk}.{secrets.token_urlsafe(32)}"
        digest = _token_digest(
            raw_token, password_hash=account.password_hash, email=account.email
        )
        try:
            reset, _ = AdminPasswordReset.objects.select_for_update().get_or_create(
                account=account,
                defaults={
                    "token_digest": digest,
                    "created_at": now,
                    "expires_at": expires_at,
                },
            )
        except ProgrammingError:
            raise AdminPasswordResetError(
                "管理员密码重置功能暂不可用，请稍后重试。"
            ) from None
        active_link = (
            reset.consumed_at is None
            and reset.expires_at > now
            and reset.token_digest != digest
        )
        reset.token_digest = digest
        reset.created_at = now
        reset.expires_at = expires_at
        reset.consumed_at = None
        reset.save(
            update_fields=("token_digest", "created_at", "expires_at", "consumed_at")
        )
        SecurityEvent.objects.create(
            event_type="ADMIN_PASSWORD_RESET_LINK_ISSUED",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"validity_minutes": 30},
        )
        audit_writer(
            action="accounts.password_reset.link.request",
            target_id=str(account.pk),
            actor_id=actor_id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"active_link": active_link},
            after={"active_link": True, "validity_minutes": 30},
        )

    try:
        from apps.navigation.public import public_site_presentation

        site_name = public_site_presentation().site_name
        reset_path = reverse("accounts:admin-password-reset")
        reset_url = f"{settings.SITE_BASE_URL.rstrip('/')}{reset_path}#{raw_token}"
        _send_reset_email(
            recipient=account.email, site_name=site_name, reset_url=reset_url
        )
    except Exception:
        failed_at = max(timezone.now(), now + timedelta(microseconds=1))
        AdminPasswordReset.objects.filter(
            account_id=account_id,
            token_digest=digest,
            consumed_at__isnull=True,
        ).update(expires_at=failed_at, consumed_at=failed_at)
        raise AdminPasswordResetError("重置邮件发送失败，请稍后重试。") from None

    return IssuedAdminPasswordReset(expires_at=expires_at)


def reset_password_with_admin_link(
    *,
    token: str,
    new_password: str,
    client_ip: str,
    trace_code: str,
) -> None:
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise AdminPasswordResetError(str(exc)) from None
    if not isinstance(token, str) or not _TOKEN_PATTERN.fullmatch(token):
        raise AdminPasswordResetError("重置链接无效或已过期，请联系管理员重新发送。")

    try:
        account_id = UUID(token.partition(".")[0])
    except ValueError:
        raise AdminPasswordResetError(
            "重置链接无效或已过期，请联系管理员重新发送。"
        ) from None
    now = timezone.now()
    with transaction.atomic():
        account = Account.objects.select_for_update().filter(pk=account_id).first()
        if account is None:
            raise AdminPasswordResetError(
                "重置链接无效或已过期，请联系管理员重新发送。"
            )
        try:
            reset = (
                AdminPasswordReset.objects.select_for_update()
                .filter(account_id=account.pk)
                .first()
            )
        except ProgrammingError:
            raise AdminPasswordResetError(
                "密码重置功能暂不可用，请稍后联系管理员。"
            ) from None
        digest = _token_digest(
            token, password_hash=account.password_hash, email=account.email
        )
        if (
            reset is None
            or reset.consumed_at is not None
            or reset.expires_at <= now
            or not hmac.compare_digest(reset.token_digest, digest)
        ):
            raise AdminPasswordResetError(
                "重置链接无效或已过期，请联系管理员重新发送。"
            )

        account.set_password(new_password)
        account.must_change_password = False
        account.save(
            update_fields=("password_hash", "must_change_password", "updated_at")
        )
        LoginSession.objects.filter(
            account_id=account.pk, revoked_at__isnull=True
        ).update(revoked_at=now)
        reset.consumed_at = now
        reset.save(update_fields=("consumed_at",))
        SecurityEvent.objects.create(
            event_type="ADMIN_PASSWORD_RESET_LINK_COMPLETED",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={},
        )
