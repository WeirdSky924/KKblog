from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import (
    AdapterResult,
    CollectedOpportunity,
    FetchClient,
    published_at_from_mapping,
)
from .http import MAX_ADAPTER_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = "https://ehr-headcount.qunhequnhe.com/api/v1/moka/job/search"
_SOURCE_PATH = "/pub/hr-recruit/campus/postlist"
_SOURCE_KINDS = {"72628": "algorithm", "66890": "development"}
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_ALGORITHM = re.compile(r"算法|大模型|机器学习|深度学习|计算机视觉|AIGC|LLM", re.I)


def _source_kind(source_url: str) -> str:
    parsed = urlsplit(source_url)
    anchors = parse_qs(parsed.query).get("post", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.kujiale.com"
        or parsed.path != _SOURCE_PATH
        or len(anchors) != 1
        or anchors[0] not in _SOURCE_KINDS
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    return _SOURCE_KINDS[anchors[0]]


def _payload(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    data = payload.get("d") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("c") not in (0, "0")
        or not isinstance(data, dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return data


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    labels = []
    for row in value:
        if not isinstance(row, dict):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        name = row.get("name")
        if isinstance(name, str) and name.strip():
            labels.append(name.strip())
    return tuple(dict.fromkeys(labels))


def _cities(value: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    displays = []
    cities = []
    for row in value:
        if not isinstance(row, dict):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        province = row.get("province")
        city = row.get("city")
        parts = tuple(
            dict.fromkeys(
                item.strip()
                for item in (province, city)
                if isinstance(item, str) and item.strip()
            )
        )
        if parts:
            displays.append("·".join(parts))
        if isinstance(city, str) and city.strip():
            cities.append(city.strip())
        elif isinstance(province, str) and province.strip():
            cities.append(province.strip())
    return tuple(dict.fromkeys(displays)), tuple(dict.fromkeys(cities))


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("jobId")
    title = row.get("title")
    if (
        not isinstance(job_id, str)
        or not job_id.strip()
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    categories = _labels(row.get("functions"))
    displays, cities = _cities(row.get("locations"))
    commitment = row.get("commitment")
    internship = commitment == "实习" or "实习" in title
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            f"https://www.kujiale.com/pub/hr-recruit/campus/postdetail/{job_id.strip()}"
        ),
        recruitment_type="INTERNSHIP" if internship else "CAMPUS",
        plan="实习招聘" if internship else "校园招聘",
        location_text="、".join(displays) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=_cohorts(title, row.get("description")),
        published_at=published_at_from_mapping(row),
    )


class KujialeAdapter:
    key = "kujiale-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        _source_kind(source_url)
        return "https://www.kujiale.com/pub/hr-recruit/campus/postlist"

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
        kind = _source_kind(source_url)
        max_pages = config.get("_max_pages", 50)
        max_opportunities = config.get("_max_opportunities", 5000)
        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or not 1 <= max_pages <= 100
            or isinstance(max_opportunities, bool)
            or not isinstance(max_opportunities, int)
            or not 1 <= max_opportunities <= 5000
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")

        page_size = 100
        offset = 0
        total = None
        opportunities = []
        pages_read = 0
        truncated = False
        while True:
            heartbeat()
            query = urlencode(
                {
                    "limit": page_size,
                    "offset": offset,
                    "mode": "campus",
                }
            )
            data = _payload(
                client.get(
                    f"{_API}?{query}",
                    max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
                )
            )
            rows = data.get("jobs")
            current_total = data.get("total")
            if (
                not isinstance(rows, list)
                or isinstance(current_total, bool)
                or not isinstance(current_total, int)
                or current_total < 0
                or (total is not None and current_total != total)
                or offset + len(rows) > current_total
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = current_total
            parsed = tuple(_job(row) for row in rows)
            technical = tuple(item for item in parsed if "技术" in item.category_labels)
            opportunities.extend(
                item
                for item in technical
                if bool(_ALGORITHM.search(item.title)) == (kind == "algorithm")
            )
            pages_read += 1
            offset += len(rows)
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if offset >= total:
                break
            if not rows:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            if len(opportunities) == max_opportunities or pages_read >= max_pages:
                truncated = True
                break

        categories = tuple(
            dict.fromkeys(
                label for item in opportunities for label in item.category_labels
            )
        )
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
            opportunities=tuple(opportunities),
            category_labels=categories,
            city_labels=cities,
            cohort_labels=cohorts,
            pages_read=max(1, pages_read),
            truncated=truncated,
        )


KUJIALE_ADAPTER = KujialeAdapter()

__all__ = ["KUJIALE_ADAPTER", "KujialeAdapter"]
