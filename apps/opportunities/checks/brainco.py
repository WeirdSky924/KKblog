from __future__ import annotations

import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_ADAPTER_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_SOURCE_URL = "https://www.brainco.cn/recruit/jobs"
_PROBE_URL = "https://www.brainco.cn/sitemap.xml"
_PUSH_PREFIX = "self.__next_f.push("
_INITIAL_JOBS = '"initialJobs":'
_IDENTIFIER = re.compile(r"[a-z0-9]{8,64}\Z", re.I)
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_CITY_SEPARATOR = re.compile(r"[,，、;；/]")


class _FlightScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._in_script = False
        self._parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag.casefold() == "script":
            self._in_script = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._in_script:
            self.scripts.append("".join(self._parts))
            self._in_script = False
            self._parts = []


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.brainco.cn"
        or parsed.path != "/recruit/jobs"
        or parsed.query
        or parsed.fragment
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _jobs(response: SafeHttpResult) -> list[object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        body = response.body.decode("utf-8")
    except UnicodeDecodeError:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    parser = _FlightScripts()
    try:
        parser.feed(body)
    except Exception:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    matches = []
    decoder = json.JSONDecoder()
    for script in parser.scripts:
        text = script.strip()
        if not text.startswith(_PUSH_PREFIX) or not text.endswith(")"):
            continue
        try:
            flight = json.loads(text[len(_PUSH_PREFIX) : -1])
        except json.JSONDecodeError:
            raise SafeRequestError(
                "opportunities.adapter_response_invalid.v1"
            ) from None
        payload = (
            flight[1]
            if isinstance(flight, list)
            and len(flight) > 1
            and isinstance(flight[1], str)
            else ""
        )
        cursor = payload.find(_INITIAL_JOBS)
        if cursor < 0:
            continue
        try:
            rows, _end = decoder.raw_decode(payload[cursor + len(_INITIAL_JOBS) :])
        except json.JSONDecodeError:
            raise SafeRequestError(
                "opportunities.adapter_response_invalid.v1"
            ) from None
        if not isinstance(rows, list):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        matches.append(rows)
    if len(matches) != 1:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return matches[0]


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _cities(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        dict.fromkeys(
            label.strip() for label in _CITY_SEPARATOR.split(value) if label.strip()
        )
    )


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("documentId")
    title = row.get("title")
    employment_type = row.get("employmentType")
    nature = row.get("nature")
    if (
        not isinstance(job_id, str)
        or not _IDENTIFIER.fullmatch(job_id)
        or not isinstance(title, str)
        or not title.strip()
        or employment_type not in {"full-time", "internship"}
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    internship = employment_type == "internship" or nature == "实习"
    cities = _cities(row.get("address"))
    return CollectedOpportunity(
        title=title.strip(),
        target_url=f"{_SOURCE_URL}#job-{job_id}",
        recruitment_type="INTERNSHIP" if internship else "SOCIAL",
        plan="实习招聘" if internship else "全职招聘",
        location_text="、".join(cities) or "未公开",
        category_labels=(),
        city_labels=cities,
        cohort_labels=_cohorts(
            title,
            row.get("duties"),
            row.get("claim"),
        ),
    )


class BraincoAdapter:
    key = "brainco-v1"
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
        max_opportunities = config.get("_max_opportunities", 5000)
        if (
            isinstance(max_opportunities, bool)
            or not isinstance(max_opportunities, int)
            or not 1 <= max_opportunities <= 5000
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        heartbeat()
        rows = _jobs(
            client.get(_SOURCE_URL, max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES)
        )
        opportunities = tuple(_job(row) for row in rows)
        truncated = len(opportunities) > max_opportunities
        if truncated:
            opportunities = opportunities[:max_opportunities]
        cities = tuple(
            dict.fromkeys(label for item in opportunities for label in item.city_labels)
        )
        cohorts = tuple(
            dict.fromkeys(
                label for item in opportunities for label in item.cohort_labels
            )
        )
        return AdapterResult(
            complete=not truncated,
            opportunities=opportunities,
            city_labels=cities,
            cohort_labels=cohorts,
            pages_read=1,
            truncated=truncated,
        )


BRAINCO_ADAPTER = BraincoAdapter()

__all__ = ["BRAINCO_ADAPTER", "BraincoAdapter"]
