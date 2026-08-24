from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.accounts.network import network_subject_digest


class RateLimiterUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    retry_after: int


def _now() -> datetime:
    return timezone.localtime(timezone.now())


def _increment(key: str, *, timeout: int) -> int:
    backend = getattr(cache, "_cache", cache).__class__.__module__
    if "redis" not in backend.casefold():
        raise RateLimiterUnavailable("Redis rate limiter backend is unavailable")
    try:
        if cache.add(key, 1, timeout=timeout):
            return 1
        return int(cache.incr(key))
    except Exception as error:
        raise RateLimiterUnavailable from error


def consume_api_rate_limit(
    *,
    client_ip: str,
    minute_limit: int,
    daily_limit: int,
    now: datetime | None = None,
) -> RateLimitDecision:
    if not isinstance(client_ip, str) or not client_ip:
        raise RateLimiterUnavailable("Client identity is unavailable")
    current = now or _now()
    if current.tzinfo is None:
        raise RateLimiterUnavailable("Rate limiter clock is unavailable")
    subject = network_subject_digest(client_ip)[:32]
    minute_start = current.replace(second=0, microsecond=0)
    next_minute = minute_start + timedelta(minutes=1)
    tomorrow = (current + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    minute_ttl = max(1, int((next_minute - current).total_seconds()) + 1)
    daily_ttl = max(1, int((tomorrow - current).total_seconds()) + 1)
    minute_key = f"learning:api:rate:{subject}:m:{minute_start:%Y%m%d%H%M}"
    daily_key = f"learning:api:rate:{subject}:d:{current:%Y%m%d}"
    minute_count = _increment(minute_key, timeout=minute_ttl)
    daily_count = _increment(daily_key, timeout=daily_ttl)
    remaining = max(0, min(minute_limit - minute_count, daily_limit - daily_count))
    if minute_count > minute_limit:
        reset = minute_ttl
        return RateLimitDecision(False, minute_limit, 0, reset, reset)
    if daily_count > daily_limit:
        reset = daily_ttl
        return RateLimitDecision(False, daily_limit, 0, reset, reset)
    return RateLimitDecision(
        True,
        min(minute_limit, daily_limit),
        remaining,
        min(minute_ttl, daily_ttl),
        0,
    )


__all__ = [
    "RateLimitDecision",
    "RateLimiterUnavailable",
    "consume_api_rate_limit",
]
