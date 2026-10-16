from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.events import ACCOUNT_REGISTERED
from apps.accounts.models import Account, LoginSession, SecurityEvent
from apps.accounts.models.account import normalize_email
from apps.accounts.policies.registration import RegistrationPolicy
from apps.accounts.profile_rules import validate_nickname
from apps.accounts.services.credentials import validate_password_strength
from apps.accounts.services.invites import InviteError, redeem_invite, validate_invite
from apps.accounts.services.verification import (
    VerificationError,
    VerificationPurpose,
    VerificationStore,
    generate_code,
    verify_code,
)
from apps.accounts.services.verification import (
    request_verification_code as send_verification_code,
)
from apps.core.events import enqueue_event


class RegistrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    account: Account
    session: LoginSession
    raw_session_token: str


def _binding(*, invite_id=None) -> str:
    return str(invite_id) if invite_id else "direct-registration"


def _resolve_path(
    *, invite_code: str, policy: RegistrationPolicy, now=None
) -> tuple[object | None, str]:
    if invite_code:
        try:
            invite = validate_invite(raw_code=invite_code, now=now)
        except InviteError as exc:
            raise RegistrationError(str(exc)) from None
        return invite, _binding(invite_id=invite.id)
    if not policy.direct_enabled:
        raise RegistrationError("当前仅支持邀请码注册")
    return None, _binding()


def request_registration_code(
    *,
    email: str,
    invite_code: str,
    policy: RegistrationPolicy,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    code_generator=generate_code,
) -> None:
    invite, binding = _resolve_path(invite_code=invite_code, policy=policy)
    del invite
    try:
        send_verification_code(
            purpose=VerificationPurpose.REGISTRATION,
            email=email,
            client_ip=client_ip,
            trace_code=trace_code,
            store=store,
            code_generator=code_generator,
            binding=binding,
        )
    except (ValidationError, VerificationError) as exc:
        raise RegistrationError(str(exc)) from None


def register_account(
    *,
    email: str,
    code: str,
    password: str,
    invite_code: str,
    remember: bool,
    policy: RegistrationPolicy,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    nickname: str | None = None,
    user_agent_summary: str = "未知浏览器 · 未知设备",
) -> RegistrationResult:
    try:
        normalized_email = normalize_email(email)
        validated_nickname = (
            validate_nickname(nickname).display if nickname is not None else None
        )
        if nickname is not None and validated_nickname is None:
            raise ValidationError("请输入用户名。")
        validate_password_strength(password)
        invite, binding = _resolve_path(invite_code=invite_code, policy=policy)
        verify_code(
            purpose=VerificationPurpose.REGISTRATION,
            email=normalized_email,
            code=code,
            store=store,
            binding=binding,
            client_ip=client_ip,
            trace_code=trace_code,
        )
    except (ValidationError, VerificationError, InviteError) as exc:
        raise RegistrationError(str(exc)) from None
    try:
        with transaction.atomic():
            account = Account.objects.create_account(
                email=normalized_email,
                password=password,
                nickname=validated_nickname,
            )
            if invite is not None:
                redeem_invite(raw_code=invite_code, account_id=account.id)
            raw_token, session = LoginSession.issue(
                account=account,
                remember=remember,
                client_ip=client_ip,
                user_agent_summary=user_agent_summary,
            )
            SecurityEvent.objects.create(
                event_type="ACCOUNT_REGISTERED",
                account=account,
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"registration_path": "invite" if invite else "direct"},
            )
            enqueue_event(
                ACCOUNT_REGISTERED,
                aggregate_type="account",
                aggregate_id=str(account.id),
                actor_id=account.id,
                trace_code=trace_code,
                payload={},
            )
    except IntegrityError:
        raise RegistrationError("邮箱或用户名已被使用") from None
    return RegistrationResult(
        account=account, session=session, raw_session_token=raw_token
    )
