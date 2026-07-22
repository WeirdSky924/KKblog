from collections.abc import Callable
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Account, LoginSession, SecurityEvent
from apps.accounts.models.account import normalize_email
from apps.accounts.services.restrictions import RestrictionStore
from apps.accounts.services.verification import (
    VerificationError,
    VerificationPurpose,
    VerificationStore,
    generate_code,
    request_verification_code,
    verify_code,
)
from apps.core.time.clock import Clock


class CredentialError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True, slots=True)
class RotatedCredential:
    session: LoginSession
    raw_token: str


def validate_password_strength(value: str) -> None:
    categories = (
        any(char.isupper() for char in value),
        any(char.islower() for char in value),
        any(char.isdigit() for char in value),
        any(not char.isalnum() for char in value),
    )
    if len(value) < 8 or sum(categories) < 2:
        raise ValidationError("密码至少 8 位，且需包含至少两类字符")


def request_password_reset_code(
    *,
    email: str,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    code_generator: Callable[[], str] = generate_code,
    restriction_store: RestrictionStore | None = None,
    clock: Clock | None = None,
) -> None:
    try:
        normalized = normalize_email(email)
    except ValidationError as exc:
        raise CredentialError("无法发送验证码") from exc
    account = Account.objects.filter(email=normalized).first()
    restrictions = restriction_store or store.restrictions
    if account is not None and restrictions.is_login_restricted(
        account_id=account.id, clock=clock
    ):
        SecurityEvent.objects.create(
            event_type="LOGIN_RESTRICTED",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"method": "password_reset_request"},
        )
        raise CredentialError("该账号暂时限制登录")
    try:
        request_verification_code(
            purpose=VerificationPurpose.PASSWORD_RESET,
            email=normalized,
            client_ip=client_ip,
            trace_code=trace_code,
            store=store,
            account_id=account.id if account else None,
            code_generator=code_generator,
            restriction_store=restrictions,
            clock=clock,
        )
    except VerificationError as exc:
        raise CredentialError(str(exc)) from None


def reset_password(
    *,
    email: str,
    code: str,
    new_password: str,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    restriction_store: RestrictionStore | None = None,
    clock: Clock | None = None,
) -> None:
    try:
        normalized = normalize_email(email)
        account = Account.objects.filter(email=normalized).first()
        restrictions = restriction_store or store.restrictions
        if account is not None and restrictions.is_login_restricted(
            account_id=account.id, clock=clock
        ):
            SecurityEvent.objects.create(
                event_type="LOGIN_RESTRICTED",
                account=account,
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"method": "password_reset"},
            )
            raise CredentialError("该账号暂时限制登录")
        validate_password_strength(new_password)
        verify_code(
            purpose=VerificationPurpose.PASSWORD_RESET,
            email=normalized,
            code=code,
            store=store,
            client_ip=client_ip,
            trace_code=trace_code,
            account_id=account.id if account else None,
        )
    except CredentialError:
        raise
    except (ValidationError, VerificationError):
        raise CredentialError("验证码无效或已失效", field="code") from None
    with transaction.atomic():
        account = Account.objects.select_for_update().filter(email=normalized).first()
        if account is None:
            raise CredentialError("验证码无效或已失效", field="code")
        account.set_password(new_password)
        account.must_change_password = False
        account.save(
            update_fields=("password_hash", "must_change_password", "updated_at")
        )
        LoginSession.objects.filter(account=account, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        SecurityEvent.objects.create(
            event_type="PASSWORD_RESET",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={},
        )


def _locked_current_session(*, account_id, current_session_id) -> LoginSession:
    session = (
        LoginSession.objects.select_for_update()
        .filter(pk=current_session_id, account_id=account_id)
        .first()
    )
    if session is None or not session.is_active():
        raise CredentialError("当前会话已失效")
    return session


def change_password(
    *,
    account_id,
    current_session_id,
    current_password: str,
    new_password: str,
    client_ip: str,
    trace_code: str,
) -> RotatedCredential:
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise CredentialError(str(exc), field="new_password") from None
    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=account_id)
        session = _locked_current_session(
            account_id=account_id, current_session_id=current_session_id
        )
        if not account.check_password(current_password):
            raise CredentialError("当前密码不正确", field="current_password")
        account.set_password(new_password)
        account.must_change_password = False
        account.save(
            update_fields=("password_hash", "must_change_password", "updated_at")
        )
        now = timezone.now()
        LoginSession.objects.filter(
            account_id=account_id, revoked_at__isnull=True
        ).exclude(pk=session.pk).update(revoked_at=now)
        raw_token = session.rotate_token()
        SecurityEvent.objects.create(
            event_type="PASSWORD_CHANGED",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={},
        )
        return RotatedCredential(session=session, raw_token=raw_token)


def request_new_email_code(
    *,
    account_id,
    new_email: str,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    code_generator: Callable[[], str] = generate_code,
) -> None:
    if not Account.objects.filter(pk=account_id, status=Account.Status.ACTIVE).exists():
        raise CredentialError("当前会话已失效")
    try:
        request_verification_code(
            purpose=VerificationPurpose.NEW_EMAIL,
            email=new_email,
            client_ip=client_ip,
            trace_code=trace_code,
            store=store,
            account_id=account_id,
            code_generator=code_generator,
            binding=str(account_id),
        )
    except (ValidationError, VerificationError) as exc:
        raise CredentialError(str(exc)) from None


def change_email(
    *,
    account_id,
    current_session_id,
    new_email: str,
    code: str,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
) -> RotatedCredential:
    try:
        normalized = normalize_email(new_email)
        verify_code(
            purpose=VerificationPurpose.NEW_EMAIL,
            email=normalized,
            code=code,
            store=store,
            binding=str(account_id),
            client_ip=client_ip,
            trace_code=trace_code,
            account_id=account_id,
        )
    except (ValidationError, VerificationError):
        raise CredentialError("验证码无效或已失效", field="code") from None
    try:
        with transaction.atomic():
            account = Account.objects.select_for_update().get(pk=account_id)
            session = _locked_current_session(
                account_id=account_id, current_session_id=current_session_id
            )
            account.email = normalized
            account.save(update_fields=("email", "updated_at"))
            raw_token = session.rotate_token()
            SecurityEvent.objects.create(
                event_type="EMAIL_CHANGED",
                account=account,
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={},
            )
            return RotatedCredential(session=session, raw_token=raw_token)
    except IntegrityError:
        raise CredentialError("该邮箱已被使用", field="new_email") from None
