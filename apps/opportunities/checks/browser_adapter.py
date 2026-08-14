from __future__ import annotations

from collections.abc import Callable, Mapping

from .adapters import AdapterResult, CollectedOpportunity
from .browser import BrowserCollector
from .http import SafeRequestError


def _limits(config: Mapping[str, object]) -> tuple[int, int, int]:
    values = (
        (config.get("_max_pages", 50), 1, 100),
        (config.get("_max_opportunities", 5000), 1, 5000),
        (config.get("_max_duration_seconds", 600), 1, 600),
    )
    result = []
    for value, minimum, maximum in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not minimum <= value <= maximum
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        result.append(value)
    return tuple(result)


def _text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return normalized


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 100:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    labels = []
    for item in value:
        label = _text(item, maximum=100)
        if label not in labels:
            labels.append(label)
    return tuple(labels)


def _candidate(value: object) -> CollectedOpportunity:
    if not isinstance(value, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    expected = {
        "title",
        "target_url",
        "recruitment_type",
        "plan",
        "location_text",
        "category_labels",
        "city_labels",
        "cohort_labels",
    }
    if set(value) != expected:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return CollectedOpportunity(
        title=_text(value["title"], maximum=200),
        target_url=_text(value["target_url"], maximum=2048),
        recruitment_type=_text(value["recruitment_type"], maximum=20),
        plan=_text(value["plan"], maximum=200),
        location_text=_text(value["location_text"], maximum=300),
        category_labels=_labels(value["category_labels"]),
        city_labels=_labels(value["city_labels"]),
        cohort_labels=_labels(value["cohort_labels"]),
    )


class BrowserSourceAdapter:
    browser_required = True
    browser_collection_enabled = True
    authoritative_listing = True

    def __init__(
        self,
        *,
        key: str,
        source_validator: Callable[[str], None],
        allowed_hosts: frozenset[str],
        collector: BrowserCollector | None = None,
    ) -> None:
        self.key = key
        self._source_validator = source_validator
        self._allowed_hosts = allowed_hosts
        self._collector = collector or BrowserCollector()

    def collect(
        self,
        *,
        source_url: str,
        config: Mapping[str, object],
        client,
        initial_response,
        heartbeat,
    ) -> AdapterResult:
        del client, initial_response
        self._source_validator(source_url)
        max_pages, max_opportunities, duration = _limits(config)
        heartbeat()
        raw = self._collector.collect(
            adapter_key=self.key,
            source_url=source_url,
            allowed_hosts=self._allowed_hosts,
            max_pages=max_pages,
            max_opportunities=max_opportunities,
            timeout_seconds=duration,
        )
        heartbeat()
        opportunities = raw.get("opportunities")
        if not isinstance(opportunities, list):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        candidates = tuple(_candidate(item) for item in opportunities)
        complete = raw.get("complete")
        pages_read = raw.get("pages_read")
        if (
            type(complete) is not bool
            or isinstance(pages_read, bool)
            or not isinstance(pages_read, int)
            or not 1 <= pages_read <= max_pages
            or len(candidates) > max_opportunities
        ):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        return AdapterResult(
            complete=complete,
            opportunities=candidates,
            category_labels=_labels(raw.get("category_labels")),
            city_labels=_labels(raw.get("city_labels")),
            cohort_labels=_labels(raw.get("cohort_labels")),
            pages_read=pages_read,
            truncated=not complete,
        )


__all__ = ["BrowserSourceAdapter"]
