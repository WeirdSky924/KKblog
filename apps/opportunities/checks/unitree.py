from __future__ import annotations

import re
from collections.abc import Mapping
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_ADAPTER_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_SOURCE_URL = "https://www.unitree.com/cn/position"
_PROBE_URL = "https://www.unitree.com/sitemap.xml"
_POSITION_PATH = re.compile(r"/cn/position/(\d{8,24})\Z")
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _normalized_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


class _PositionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.positions: list[dict[str, object]] = []
        self._current: dict[str, object] | None = None
        self._field = ""
        self._suppressed = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if self._current is None and tag == "a":
            href = attributes.get("href", "")
            classes = set(attributes.get("class", "").split())
            match = _POSITION_PATH.fullmatch(href)
            if match is not None and "link" in classes:
                self._current = {
                    "id": match.group(1),
                    "title": [],
                    "base": [],
                    "text": [],
                }
            return
        if self._current is None:
            return
        classes = set(attributes.get("class", "").split())
        if tag == "p" and "title" in classes:
            self._field = "title"
        elif tag == "p" and "base-info" in classes:
            self._field = "base"
        elif tag == "span" and self._field == "title":
            self._suppressed += 1

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "span" and self._suppressed:
            self._suppressed -= 1
        elif tag == "p":
            self._field = ""
            self._suppressed = 0
        elif tag == "a":
            self.positions.append(self._current)
            self._current = None
            self._field = ""
            self._suppressed = 0

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        self._current["text"].append(data)
        if self._field and not self._suppressed:
            self._current[self._field].append(data)


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.unitree.com"
        or parsed.path != "/cn/position"
        or parsed.query
        or parsed.fragment
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _positions(response: SafeHttpResult) -> tuple[CollectedOpportunity, ...]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        body = response.body.decode("utf-8")
    except UnicodeDecodeError:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    parser = _PositionParser()
    try:
        parser.feed(body)
    except Exception:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not parser.positions:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    result = []
    seen = set()
    for row in parser.positions:
        job_id = row["id"]
        title = _normalized_text(row["title"])
        if job_id in seen or not title:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        seen.add(job_id)
        base_parts = [
            value.strip()
            for value in _normalized_text(row["base"]).split("|")
            if value.strip()
        ]
        cities = tuple(base_parts[:1])
        categories = tuple(base_parts[1:2])
        cohorts = tuple(
            dict.fromkeys(
                f"20{year}届" for year in _COHORT.findall(_normalized_text(row["text"]))
            )
        )
        result.append(
            CollectedOpportunity(
                title=title,
                target_url=f"{_SOURCE_URL}/{job_id}",
                recruitment_type="SOCIAL",
                plan="社会招聘",
                location_text="、".join(cities) or "未公开",
                category_labels=categories,
                city_labels=cities,
                cohort_labels=cohorts,
            )
        )
    return tuple(result)


class UnitreeAdapter:
    key = "unitree-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        _source(source_url)
        return _PROBE_URL

    def collect(
        self,
        *,
        source_url: str,
        config: Mapping[str, object],
        client: FetchClient,
        initial_response: SafeHttpResult,
        heartbeat,
    ) -> AdapterResult:
        del initial_response
        _source(source_url)
        maximum = config.get("_max_opportunities", 5000)
        if (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or not 1 <= maximum <= 5000
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        heartbeat()
        opportunities = _positions(
            client.get(
                _SOURCE_URL,
                max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
            )
        )
        truncated = len(opportunities) > maximum
        if truncated:
            opportunities = opportunities[:maximum]
        return AdapterResult(
            complete=not truncated,
            opportunities=opportunities,
            category_labels=tuple(
                dict.fromkeys(
                    label for item in opportunities for label in item.category_labels
                )
            ),
            city_labels=tuple(
                dict.fromkeys(
                    label for item in opportunities for label in item.city_labels
                )
            ),
            cohort_labels=tuple(
                dict.fromkeys(
                    label for item in opportunities for label in item.cohort_labels
                )
            ),
            pages_read=1,
            truncated=truncated,
        )


UNITREE_ADAPTER = UnitreeAdapter()

__all__ = ["UNITREE_ADAPTER", "UnitreeAdapter"]
