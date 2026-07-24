import hashlib
import hmac
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

from apps.core.ids import new_ulid


class CommentCooldownUnavailable(RuntimeError):
    pass


class CommentCooldownActive(ValueError):
    def __init__(self, remaining_seconds: int) -> None:
        self.remaining_seconds = max(1, int(remaining_seconds))
        super().__init__("评论提交过于频繁")


@dataclass(frozen=True, slots=True)
class CooldownReservation:
    key: str
    token: str


class CommentCooldownStore:
    _RESERVE_SCRIPT = """
    local created = redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2])
    if created then return {1, tonumber(ARGV[2])} end
    local remaining = redis.call('TTL', KEYS[1])
    if remaining < 1 then remaining = 1 end
    return {0, remaining}
    """
    _ROLLBACK_SCRIPT = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    end
    return 0
    """

    def __init__(self, *, client: Redis, namespace: str = "kaj") -> None:
        self.client = client
        self.namespace = namespace

    @staticmethod
    def _subject(subject_kind: str, subject_value: str) -> tuple[str, str]:
        if subject_kind == "ACCOUNT":
            try:
                return "account", str(UUID(str(subject_value)))
            except (TypeError, ValueError):
                raise ValueError("Invalid comment cooldown subject") from None
        if subject_kind == "IP":
            try:
                parsed = ip_address(subject_value)
            except (TypeError, ValueError):
                raise ValueError("Invalid comment cooldown subject") from None
            if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
                parsed = parsed.ipv4_mapped
            return "ip", str(parsed)
        raise ValueError("Invalid comment cooldown subject")

    def _key(self, subject_kind: str, subject_value: str) -> str:
        kind, normalized = self._subject(subject_kind, subject_value)
        digest = hmac.new(
            settings.SECRET_KEY.encode(),
            f"comment-cooldown:{kind}:{normalized}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{self.namespace}:comment-cooldown:{kind}:{digest}"

    def reserve(
        self, *, subject_kind: str, subject_value: str, ttl_seconds: int
    ) -> CooldownReservation:
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= 3_600
        ):
            raise ValueError("Invalid comment cooldown duration")
        key = self._key(subject_kind, subject_value)
        token = new_ulid()
        try:
            created, remaining = self.client.eval(
                self._RESERVE_SCRIPT,
                1,
                key,
                token,
                ttl_seconds,
            )
        except RedisError:
            raise CommentCooldownUnavailable("评论冷却服务暂不可用") from None
        if int(created) != 1:
            raise CommentCooldownActive(int(remaining))
        return CooldownReservation(key=key, token=token)

    def rollback(self, reservation: CooldownReservation) -> bool:
        if not isinstance(reservation, CooldownReservation):
            raise TypeError("reservation must be a CooldownReservation")
        try:
            removed = self.client.eval(
                self._ROLLBACK_SCRIPT,
                1,
                reservation.key,
                reservation.token,
            )
        except RedisError:
            raise CommentCooldownUnavailable("评论冷却服务暂不可用") from None
        return int(removed) == 1


def default_comment_cooldown_store() -> CommentCooldownStore:
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        raise CommentCooldownUnavailable("评论冷却服务暂不可用")
    namespace = getattr(settings, "COMMENTS_COOLDOWN_NAMESPACE", "kaj")
    return CommentCooldownStore(
        client=Redis.from_url(redis_url, decode_responses=False, socket_timeout=2),
        namespace=namespace,
    )
