from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from .http import SafeHttpResult


class FetchClient(Protocol):
    def get(self, url: str, **limits) -> SafeHttpResult: ...

    def post_json(
        self, url: str, payload: Mapping[str, object], **limits
    ) -> SafeHttpResult: ...


_ADAPTER_KEY = re.compile(r"[a-z][a-z0-9-]{1,79}\Z")


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
    "register_adapter",
    "registered_adapters",
]
