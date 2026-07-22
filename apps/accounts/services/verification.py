import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from enum import StrEnum

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from redis import Redis

from apps.accounts.models import SecurityEvent
from apps.accounts.models.account import normalize_email
from apps.accounts.services.restrictions import (
    RestrictionError,
    RestrictionStore,
)
from apps.core.time.clock import Clock

CODE_TTL_SECONDS = 600
RESEND_SECONDS = 60
MAX_FAILURES = 5
_CODE = re.compile(r"[0-9]{6}\Z")


class VerificationPurpose(StrEnum):
    REGISTRATION = "registration"
    LOGIN = "login"
    PASSWORD_RESET = "password_reset"
    NEW_EMAIL = "new_email"


class VerificationError(ValueError):
    pass


def _subject_digest(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"verification-subject:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _code_digest(*, purpose: VerificationPurpose, email: str, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"verification-code:{purpose.value}:{email}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _binding_digest(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"verification-binding:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


class VerificationStore:
    _ISSUE_SCRIPT = """
    if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
    redis.call('SET', KEYS[1], '1', 'EX', ARGV[2])
    redis.call('HSET', KEYS[2], 'digest', ARGV[1], 'attempts', '0', 'binding', ARGV[4])
    redis.call('EXPIRE', KEYS[2], ARGV[3])
    return 1
    """
    _VERIFY_SCRIPT = """
    local expected = redis.call('HGET', KEYS[1], 'digest')
    if not expected then return 0 end
    local binding = redis.call('HGET', KEYS[1], 'binding')
    if binding ~= ARGV[3] then return 0 end
    if expected == ARGV[1] then redis.call('DEL', KEYS[1]); return 1 end
    local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
    if attempts >= tonumber(ARGV[2]) then redis.call('DEL', KEYS[1]); return -attempts end
    return -attempts
    """

    def __init__(
        self,
        *,
        client: Redis,
        namespace: str = "kaj",
        restriction_store: RestrictionStore | None = None,
    ) -> None:
        self.client = client
        self.namespace = namespace
        self.restrictions = restriction_store or RestrictionStore(
            client=client, namespace=namespace
        )

    def _email_hash(self, email: str) -> str:
        return _subject_digest(email)

    def challenge_key(self, *, purpose: VerificationPurpose, email: str) -> str:
        return (
            f"{self.namespace}:verification:challenge:{purpose.value}:"
            f"{self._email_hash(email)}"
        )

    def resend_key(self, *, email: str) -> str:
        return f"{self.namespace}:verification:resend:{self._email_hash(email)}"

    def issue(
        self,
        *,
        purpose: VerificationPurpose,
        email: str,
        digest: str,
        binding: str = "",
    ) -> None:
        result = self.client.eval(
            self._ISSUE_SCRIPT,
            2,
            self.resend_key(email=email),
            self.challenge_key(purpose=purpose, email=email),
            digest,
            RESEND_SECONDS,
            CODE_TTL_SECONDS,
            _binding_digest(binding),
        )
        if result != 1:
            raise VerificationError("请稍后再发送验证码")

    def verify(
        self,
        *,
        purpose: VerificationPurpose,
        email: str,
        digest: str,
        binding: str = "",
    ) -> None:
        result = self.client.eval(
            self._VERIFY_SCRIPT,
            1,
            self.challenge_key(purpose=purpose, email=email),
            digest,
            MAX_FAILURES,
            _binding_digest(binding),
        )
        if result != 1:
            raise VerificationError("验证码无效或已失效")

    def rollback_issue(self, *, purpose: VerificationPurpose, email: str) -> None:
        self.client.delete(
            self.challenge_key(purpose=purpose, email=email),
            self.resend_key(email=email),
        )

    def clear_send_restriction(self, *, email: str) -> None:
        self.client.delete(self.resend_key(email=email))


def default_verification_store() -> VerificationStore:
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        raise VerificationError("验证码服务暂不可用")
    namespace = getattr(settings, "ACCOUNT_RESTRICTION_NAMESPACE", "kaj")
    return VerificationStore(
        client=Redis.from_url(redis_url, decode_responses=False, socket_timeout=2),
        namespace=namespace,
    )


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def request_verification_code(
    *,
    purpose: VerificationPurpose,
    email: str,
    client_ip: str,
    trace_code: str,
    store: VerificationStore,
    account_id=None,
    code_generator: Callable[[], str] = generate_code,
    binding: str = "",
    restriction_store: RestrictionStore | None = None,
    clock: Clock | None = None,
) -> None:
    normalized = normalize_email(email)
    restrictions = restriction_store or store.restrictions
    try:
        reservation = restrictions.reserve_verification_send(
            email=normalized, client_ip=client_ip, clock=clock
        )
    except RestrictionError as exc:
        SecurityEvent.objects.create(
            event_type="VERIFICATION_SEND_RESTRICTED",
            account_id=account_id,
            subject_digest=_subject_digest(normalized),
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"purpose": purpose.value},
        )
        raise VerificationError(str(exc)) from None
    code = code_generator()
    if not _CODE.fullmatch(code):
        restrictions.rollback_verification_send(reservation)
        raise VerificationError("验证码生成失败")
    digest = _code_digest(purpose=purpose, email=normalized, code=code)
    issued = False
    try:
        store.issue(purpose=purpose, email=normalized, digest=digest, binding=binding)
        issued = True
        message = render_to_string(
            "accounts/email/verification.txt",
            {"code": code, "minutes": 10},
        )
        send_mail(
            subject="Kaj 的小房间验证码",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[normalized],
            fail_silently=False,
        )
        SecurityEvent.objects.create(
            event_type="VERIFICATION_CODE_SENT",
            account_id=account_id,
            subject_digest=_subject_digest(normalized),
            client_ip=client_ip,
            trace_code=trace_code,
            safe_summary={"purpose": purpose.value},
        )
    except Exception:
        if issued:
            store.rollback_issue(purpose=purpose, email=normalized)
        restrictions.rollback_verification_send(reservation)
        raise


def verify_code(
    *,
    purpose: VerificationPurpose,
    email: str,
    code: str,
    store: VerificationStore,
    binding: str = "",
    client_ip: str = "",
    trace_code: str = "",
    account_id=None,
) -> None:
    normalized = normalize_email(email)
    outcome = "succeeded"
    try:
        if not _CODE.fullmatch(code):
            raise VerificationError("验证码无效或已失效")
        store.verify(
            purpose=purpose,
            email=normalized,
            digest=_code_digest(purpose=purpose, email=normalized, code=code),
            binding=binding,
        )
    except VerificationError:
        outcome = "failed"
        raise
    finally:
        if client_ip and trace_code:
            SecurityEvent.objects.create(
                event_type="VERIFICATION_CODE_CHECKED",
                account_id=account_id,
                subject_digest=_subject_digest(normalized),
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"purpose": purpose.value, "outcome": outcome},
            )
