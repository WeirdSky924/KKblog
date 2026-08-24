from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import isfinite
from types import MappingProxyType
from typing import Protocol
from zoneinfo import ZoneInfo

from .http import SafeHttpResult


class FetchClient(Protocol):
    def get(self, url: str, **limits) -> SafeHttpResult: ...

    def post_json(
        self, url: str, payload: Mapping[str, object], **limits
    ) -> SafeHttpResult: ...


_ADAPTER_KEY = re.compile(r"[a-z][a-z0-9-]{1,79}\Z")
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_PUBLICATION_KEYS = (
    "published_at",
    "publishedAt",
    "publishedTime",
    "publishedDate",
    "publish_time",
    "publishTime",
    "publishDate",
    "releaseTime",
    "releaseDate",
    "releasedAt",
    "jobPublishTime",
    "jobPublishDate",
    "positionPublishTime",
    "positionPublishDate",
    "postingDate",
    "postDate",
    "onlineTime",
    "createTime",
    "createdAt",
    "createDate",
    "JobAdCreateDate",
    "JobAdPublishDate",
    "JobAdPublishTime",
    "JobAdStartDate",
    "PublishDate",
    "CreateTime",
)
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
)


def _valid_publication_time(value: datetime) -> datetime | None:
    normalized = (
        value.replace(tzinfo=_SHANGHAI) if value.tzinfo is None else value
    ).astimezone(UTC)
    return normalized if 2000 <= normalized.year <= 2100 else None


def parse_published_at(value: object) -> datetime | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return _valid_publication_time(value)
    if isinstance(value, date):
        return _valid_publication_time(datetime.combine(value, time.min))
    if isinstance(value, int | float):
        try:
            numeric = float(value)
        except (OverflowError, ValueError):
            return None
        if not isfinite(numeric):
            return None
        timestamp = numeric / (1000 if abs(numeric) >= 100_000_000_000 else 1)
        try:
            return _valid_publication_time(datetime.fromtimestamp(timestamp, tz=UTC))
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{8}", raw):
        try:
            return _valid_publication_time(datetime.strptime(raw, "%Y%m%d"))
        except ValueError:
            return None
    dotnet = re.fullmatch(r"/?Date\((-?\d{10,13})(?:[+-]\d{4})?\)/?", raw)
    if dotnet:
        return parse_published_at(dotnet.group(1))
    if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        try:
            return parse_published_at(float(raw))
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        return _valid_publication_time(parsed)
    for pattern in _DATE_FORMATS:
        try:
            return _valid_publication_time(datetime.strptime(raw, pattern))
        except ValueError:
            continue
    return None


def published_at_from_mapping(value: Mapping[str, object]) -> datetime | None:
    for key in _PUBLICATION_KEYS:
        if key in value and (parsed := parse_published_at(value[key])) is not None:
            return parsed
    return None


@dataclass(frozen=True, slots=True)
class CollectedOpportunity:
    title: str
    target_url: str
    recruitment_type: str
    plan: str
    location_text: str
    category_labels: tuple[str, ...]
    city_labels: tuple[str, ...]
    cohort_labels: tuple[str, ...]
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AdapterResult:
    complete: bool
    opportunities: tuple[CollectedOpportunity, ...] = ()
    category_labels: tuple[str, ...] = ()
    city_labels: tuple[str, ...] = ()
    cohort_labels: tuple[str, ...] = ()
    pages_read: int = 1
    truncated: bool = False


class OpportunityAdapter(Protocol):
    key: str
    browser_required: bool
    authoritative_listing: bool

    def collect(
        self,
        *,
        source_url: str,
        config: Mapping[str, object],
        client: FetchClient,
        initial_response: SafeHttpResult,
        heartbeat: Callable[[], None],
    ) -> AdapterResult: ...


_ADAPTERS: dict[str, OpportunityAdapter] = {}


class ManualUnsupportedAdapter:
    key = "manual-unsupported-v1"
    browser_required = True
    authoritative_listing = False

    def collect(self, **kwargs):
        del kwargs
        raise RuntimeError("Unsupported adapter must not collect")


MANUAL_UNSUPPORTED_ADAPTER = ManualUnsupportedAdapter()


def register_adapter(adapter: OpportunityAdapter, *, replace: bool = False) -> None:
    key = getattr(adapter, "key", None)
    browser_required = getattr(adapter, "browser_required", None)
    authoritative_listing = getattr(adapter, "authoritative_listing", None)
    collect = getattr(adapter, "collect", None)
    if (
        not isinstance(key, str)
        or not _ADAPTER_KEY.fullmatch(key)
        or not isinstance(browser_required, bool)
        or not isinstance(authoritative_listing, bool)
        or not callable(collect)
    ):
        raise ValueError("Invalid opportunity adapter")
    current = _ADAPTERS.get(key)
    if current is not None and current is not adapter and not replace:
        raise ValueError("Opportunity adapter already registered")
    _ADAPTERS[key] = adapter


def get_adapter(key: str) -> OpportunityAdapter:
    if not isinstance(key, str) or not _ADAPTER_KEY.fullmatch(key):
        raise LookupError("Opportunity adapter is unavailable")
    try:
        return _ADAPTERS[key]
    except KeyError:
        raise LookupError("Opportunity adapter is unavailable") from None


def registered_adapters() -> Mapping[str, OpportunityAdapter]:
    return MappingProxyType(_ADAPTERS)


__all__ = [
    "AdapterResult",
    "CollectedOpportunity",
    "OpportunityAdapter",
    "get_adapter",
    "MANUAL_UNSUPPORTED_ADAPTER",
    "parse_published_at",
    "published_at_from_mapping",
    "register_adapter",
    "registered_adapters",
]
