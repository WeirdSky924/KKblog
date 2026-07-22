from collections.abc import Callable
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import Account, LoginSession, SecurityEvent
from apps.accounts.models.account import normalize_email
from apps.accounts.services.restrictions import (
    RestrictionStore,
    default_restriction_store,
)
from apps.accounts.services.verification import (
    VerificationError,
    VerificationPurpose,
    VerificationStore,
    generate_code,
    request_verification_code,
    verify_code,
)
from apps.core.time.clock import Clock


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    account: Account
    session: LoginSession
    raw_token: str


def _account_for_login(email: str) -> Account | None:
    try:
        normalized = normalize_email(email)
    except ValidationError:
        return None
    return Account.objects.filter(email=normalized).first()


def _issue(
    *,
    account: Account,
    remember: bool,
    client_ip: str,
    trace_code: str,
    method: str,
    user_agent_summary: str,
) -> AuthenticationResult:
    if account.status != Account.Status.ACTIVE:
        raise AuthenticationError("账号当前不可登录")
    with transaction.atomic():
        raw_token, session = LoginSession.issue(
            account=account,
            remember=remember,
            client_ip=client_ip,
            user_agent_summary=user_agent_summary,
        )
        SecurityEvent.objects.create(
            event_type="LOGIN_SUCCEEDED",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"method": method},
        )
    return AuthenticationResult(account=account, session=session, raw_token=raw_token)


def _raise_if_restricted(
    *,
    account: Account | None,
    restrictions: RestrictionStore,
    client_ip: str,
    trace_code: str,
    method: str,
    clock: Clock | None,
) -> None:
    if account is None or not restrictions.is_login_restricted(
        account_id=account.id, clock=clock
    ):
        return
    SecurityEvent.objects.create(
        event_type="LOGIN_RESTRICTED",
        account=account,
        client_ip=client_ip,
        trace_code=trace_code,
        safe_summary={"method": method},
    )
    raise AuthenticationError("该账号暂时限制登录")


def authenticate_password(
    *,
    email: str,
    password: str,
    remember: bool,
    client_ip: str,
    trace_code: str,
    user_agent_summary: str = "未知浏览器 · 未知设备",
    restriction_store: RestrictionStore | None = None,
    clock: Clock | None = None,
) -> AuthenticationResult:
    restrictions = restriction_store or default_restriction_store()
    account = _account_for_login(email)
    _raise_if_restricted(
        account=account,
        restrictions=restrictions,
        client_ip=client_ip,
        trace_code=trace_code,
        method="password",
        clock=clock,
    )
    if account is None or not account.check_password(password):
        SecurityEvent.objects.create(
            event_type="LOGIN_FAILED",
            account=account,
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"method": "password"},
        )
        restricted = restrictions.record_password_failure(
            email=email,
            account_id=account.id if account else None,
            clock=clock,
        )
        if restricted and account is not None:
            SecurityEvent.objects.create(
                event_type="LOGIN_RESTRICTION_APPLIED",
                account=account,
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"method": "password"},
            )
            raise AuthenticationError("该账号暂时限制登录")
        raise AuthenticationError("邮箱或密码不正确")
    if not restrictions.accept_password_success(
        email=account.email, account_id=account.id, clock=clock
    ):
        _raise_if_restricted(
            account=account,
            restrictions=restrictions,
            client_ip=client_ip,
            trace_code=trace_code,
            method="password",
            clock=clock,
        )
    return _issue(
        account=account,
        remember=remember,
        client_ip=client_ip,
        trace_code=trace_code,
        method="password",
        user_agent_summary=user_agent_summary,
    )


def request_login_code(
    *,
    email: str,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    code_generator: Callable[[], str] = generate_code,
    restriction_store: RestrictionStore | None = None,
    clock: Clock | None = None,
) -> None:
    account = _account_for_login(email)
    restrictions = restriction_store or store.restrictions
    _raise_if_restricted(
        account=account,
        restrictions=restrictions,
        client_ip=client_ip,
        trace_code=trace_code,
        method="email_code_request",
        clock=clock,
    )
    try:
        request_verification_code(
            purpose=VerificationPurpose.LOGIN,
            email=email,
            client_ip=client_ip,
            trace_code=trace_code,
            store=store,
            account_id=account.id if account else None,
            code_generator=code_generator,
            restriction_store=restrictions,
            clock=clock,
        )
    except (ValidationError, VerificationError) as exc:
        raise AuthenticationError(str(exc)) from None


def authenticate_code(
    *,
    email: str,
    code: str,
    remember: bool,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    user_agent_summary: str = "未知浏览器 · 未知设备",
    restriction_store: RestrictionStore | None = None,
    clock: Clock | None = None,
) -> AuthenticationResult:
    account = _account_for_login(email)
    restrictions = restriction_store or store.restrictions
    _raise_if_restricted(
        account=account,
        restrictions=restrictions,
        client_ip=client_ip,
        trace_code=trace_code,
        method="email_code",
        clock=clock,
    )
    try:
        verify_code(
            purpose=VerificationPurpose.LOGIN,
            email=email,
            code=code,
            store=store,
            client_ip=client_ip,
            trace_code=trace_code,
            account_id=account.id if account else None,
        )
    except (ValidationError, VerificationError):
        raise AuthenticationError("验证码无效或已失效") from None
    if account is None:
        raise AuthenticationError("账号当前不可登录")
    return _issue(
        account=account,
        remember=remember,
        client_ip=client_ip,
        trace_code=trace_code,
        method="email_code",
        user_agent_summary=user_agent_summary,
    )
