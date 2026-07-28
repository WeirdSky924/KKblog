import hashlib
import hmac
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from ipaddress import ip_address
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from redis import Redis

from apps.accounts.models import Account, RoleAssignment, SecurityEvent
from apps.accounts.models.account import normalize_email
from apps.core.time.clock import Clock, SystemClock

LOGIN_FAILURE_LIMIT = 5
LOGIN_BLOCK_SECONDS = 60 * 60
VERIFICATION_DAILY_LIMIT = 20
SHANGHAI = ZoneInfo("Asia/Shanghai")


class RestrictionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerificationReservation:
    email_key: str
    ip_key: str


@dataclass(frozen=True, slots=True)
class _SnapshotEntry:
    key: str
    value: bytes
    ttl_ms: int


class RestrictionStore:
    _RESERVE_SCRIPT = """
    local email_count = tonumber(redis.call('GET', KEYS[1]) or '0')
    local ip_count = tonumber(redis.call('GET', KEYS[2]) or '0')
    if email_count >= tonumber(ARGV[1]) or ip_count >= tonumber(ARGV[1]) then
        return 0
    end
    email_count = redis.call('INCR', KEYS[1])
    ip_count = redis.call('INCR', KEYS[2])
    if email_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
    if ip_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[2]) end
    return 1
    """
    _ROLLBACK_SCRIPT = """
    for _, key in ipairs(KEYS) do
        local current = tonumber(redis.call('GET', key) or '0')
        if current <= 1 then
            redis.call('DEL', key)
        else
            redis.call('DECR', key)
        end
    end
    return 1
    """
    _FAILURE_SCRIPT = """
    local expires_at = tonumber(redis.call('GET', KEYS[2]) or '0')
    if expires_at > 0 and expires_at <= tonumber(ARGV[1]) then
        redis.call('DEL', KEYS[2])
        expires_at = 0
    end
    if expires_at > tonumber(ARGV[1]) then return -1 end
    local failures = redis.call('INCR', KEYS[1])
    if failures >= tonumber(ARGV[2]) and ARGV[4] == '1' then
        redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[5])
        redis.call('DEL', KEYS[1])
        return -1
    end
    return failures
    """
    _BLOCKED_SCRIPT = """
    local expires_at = tonumber(redis.call('GET', KEYS[1]) or '0')
    if expires_at > 0 and expires_at <= tonumber(ARGV[1]) then
        redis.call('DEL', KEYS[1])
        return 0
    end
    if expires_at > tonumber(ARGV[1]) then return 1 end
    return 0
    """
    _SUCCESS_SCRIPT = """
    local expires_at = tonumber(redis.call('GET', KEYS[2]) or '0')
    if expires_at > 0 and expires_at <= tonumber(ARGV[1]) then
        redis.call('DEL', KEYS[2])
        expires_at = 0
    end
    if expires_at > tonumber(ARGV[1]) then return 0 end
    redis.call('DEL', KEYS[1])
    return 1
    """

    def __init__(self, *, client: Redis, namespace: str = "kaj") -> None:
        self.client = client
        self.namespace = namespace

    def _digest(self, kind: str, value: str) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode(),
            f"restriction:{kind}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def _moment(self, clock: Clock | None) -> datetime:
        return (clock or SystemClock()).now()

    def _day(self, clock: Clock | None) -> tuple[str, int]:
        local = self._moment(clock).astimezone(SHANGHAI)
        next_midnight = datetime.combine(
            local.date() + timedelta(days=1), time.min, tzinfo=SHANGHAI
        )
        return local.date().isoformat(), max(
            1, math.ceil((next_midnight - local).total_seconds())
        )

    def _verification_keys(
        self, *, email: str, client_ip: str, clock: Clock | None
    ) -> tuple[str, str, int]:
        normalized_email = normalize_email(email)
        normalized_ip = str(ip_address(client_ip))
        day, ttl = self._day(clock)
        return (
            f"{self.namespace}:verify-send:email:{day}:"
            f"{self._digest('email', normalized_email)}",
            f"{self.namespace}:verify-send:ip:{day}:"
            f"{self._digest('ip', normalized_ip)}",
            ttl,
        )

    def reserve_verification_send(
        self, *, email: str, client_ip: str, clock: Clock | None = None
    ) -> VerificationReservation:
        email_key, ip_key, ttl = self._verification_keys(
            email=email, client_ip=client_ip, clock=clock
        )
        result = self.client.eval(
            self._RESERVE_SCRIPT,
            2,
            email_key,
            ip_key,
            VERIFICATION_DAILY_LIMIT,
            ttl,
        )
        if result != 1:
            raise RestrictionError("验证码请求过于频繁")
        return VerificationReservation(email_key=email_key, ip_key=ip_key)

    def rollback_verification_send(self, reservation: VerificationReservation) -> None:
        self.client.eval(
            self._ROLLBACK_SCRIPT,
            2,
            reservation.email_key,
            reservation.ip_key,
        )

    def verification_send_counts(
        self, *, email: str, client_ip: str, clock: Clock | None = None
    ) -> tuple[int, int]:
        email_key, ip_key, _ = self._verification_keys(
            email=email, client_ip=client_ip, clock=clock
        )
        values = self.client.mget(email_key, ip_key)
        return tuple(int(value or 0) for value in values)

    def _failure_key(self, email: str) -> str:
        normalized = normalize_email(email)
        return f"{self.namespace}:login-fail:{self._digest('email', normalized)}"

    def _block_key(self, account_id) -> str:
        return f"{self.namespace}:login-block:{account_id}"

    def record_password_failure(
        self,
        *,
        email: str,
        account_id=None,
        clock: Clock | None = None,
    ) -> bool:
        now = self._moment(clock)
        expires_at = int((now + timedelta(seconds=LOGIN_BLOCK_SECONDS)).timestamp())
        result = self.client.eval(
            self._FAILURE_SCRIPT,
            2,
            self._failure_key(email),
            self._block_key(account_id or "unknown"),
            int(now.timestamp()),
            LOGIN_FAILURE_LIMIT,
            expires_at,
            "1" if account_id else "0",
            LOGIN_BLOCK_SECONDS,
        )
        return result == -1

    def is_login_restricted(self, *, account_id, clock: Clock | None = None) -> bool:
        result = self.client.eval(
            self._BLOCKED_SCRIPT,
            1,
            self._block_key(account_id),
            int(self._moment(clock).timestamp()),
        )
        return result == 1

    def accept_password_success(
        self, *, email: str, account_id, clock: Clock | None = None
    ) -> bool:
        result = self.client.eval(
            self._SUCCESS_SCRIPT,
            2,
            self._failure_key(email),
            self._block_key(account_id),
            int(self._moment(clock).timestamp()),
        )
        return result == 1

    def account_keys(self, *, account: Account, clock: Clock | None) -> tuple[str, ...]:
        email_key, _, _ = self._verification_keys(
            email=account.email, client_ip="127.0.0.1", clock=clock
        )
        return self._failure_key(account.email), self._block_key(account.id), email_key

    def ip_keys(self, *, target_ip: str, clock: Clock | None) -> tuple[str, ...]:
        _, ip_key, _ = self._verification_keys(
            email="placeholder@kaj.test", client_ip=target_ip, clock=clock
        )
        return (ip_key,)

    def snapshot_and_delete(self, keys: tuple[str, ...]) -> tuple[_SnapshotEntry, ...]:
        pipeline = self.client.pipeline(transaction=True)
        for key in keys:
            pipeline.get(key)
            pipeline.pttl(key)
        pipeline.delete(*keys)
        results = pipeline.execute()
        entries = []
        for index, key in enumerate(keys):
            value = results[index * 2]
            ttl_ms = int(results[index * 2 + 1])
            if value is not None:
                entries.append(_SnapshotEntry(key=key, value=value, ttl_ms=ttl_ms))
        return tuple(entries)

    def restore(self, entries: tuple[_SnapshotEntry, ...]) -> None:
        pipeline = self.client.pipeline(transaction=True)
        for entry in entries:
            kwargs = {"nx": True}
            if entry.ttl_ms > 0:
                kwargs["px"] = entry.ttl_ms
            pipeline.set(entry.key, entry.value, **kwargs)
        pipeline.execute()


def default_restriction_store() -> RestrictionStore:
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        raise RestrictionError("限制服务暂不可用")
    namespace = getattr(settings, "ACCOUNT_RESTRICTION_NAMESPACE", "kaj")
    return RestrictionStore(
        client=Redis.from_url(redis_url, decode_responses=False, socket_timeout=2),
        namespace=namespace,
    )


def _require_administrator(actor_id) -> None:
    if not RoleAssignment.objects.filter(
        account_id=actor_id,
        account__status=Account.Status.ACTIVE,
        role=RoleAssignment.Role.ADMINISTRATOR,
    ).exists():
        raise PermissionError("仅管理员可清除限制")


def _clear_with_audit(
    *,
    actor_id,
    target_id: str,
    affected_account_id,
    keys: tuple[str, ...],
    restriction_kind: str,
    client_ip: str,
    trace_code: str,
    store: RestrictionStore,
    audit_writer,
) -> int:
    _require_administrator(actor_id)
    snapshot = store.snapshot_and_delete(keys)
    try:
        with transaction.atomic():
            audit_writer(
                action="accounts.restriction.clear",
                actor_id=actor_id,
                target_id=target_id,
                trace_code=trace_code,
                client_ip=client_ip,
                before={"restriction_kind": restriction_kind},
                after={"restriction_kind": None},
                summary="Clear temporary account restriction",
            )
            SecurityEvent.objects.create(
                event_type="TEMPORARY_RESTRICTION_CLEARED",
                account_id=affected_account_id,
                client_ip=client_ip,
                trace_code=trace_code,
                safe_summary={"restriction_kind": restriction_kind},
            )
    except Exception:
        store.restore(snapshot)
        raise
    return len(snapshot)


def clear_account_restrictions(
    *,
    actor_id,
    target_account_id,
    client_ip: str,
    trace_code: str,
    store: RestrictionStore,
    audit_writer,
    clock: Clock | None = None,
) -> int:
    _require_administrator(actor_id)
    try:
        account = Account.objects.get(pk=target_account_id)
    except (Account.DoesNotExist, ValidationError):
        raise RestrictionError("账户不存在") from None
    return _clear_with_audit(
        actor_id=actor_id,
        target_id=str(account.id),
        affected_account_id=account.id,
        keys=store.account_keys(account=account, clock=clock),
        restriction_kind="login_and_verification_send",
        client_ip=client_ip,
        trace_code=trace_code,
        store=store,
        audit_writer=audit_writer,
    )


def clear_ip_send_restriction(
    *,
    actor_id,
    target_ip: str,
    client_ip: str,
    trace_code: str,
    store: RestrictionStore,
    audit_writer,
    clock: Clock | None = None,
) -> int:
    normalized_ip = str(ip_address(target_ip))
    target_id = store._digest("ip", normalized_ip)
    return _clear_with_audit(
        actor_id=actor_id,
        target_id=target_id,
        affected_account_id=actor_id,
        keys=store.ip_keys(target_ip=normalized_ip, clock=clock),
        restriction_kind="ip_verification_send",
        client_ip=client_ip,
        trace_code=trace_code,
        store=store,
        audit_writer=audit_writer,
    )
