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
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = "https://hr.163.com/api/hr163/position"
_SOURCE_PATH = "/job-list.html"
_DETAIL_PATH = "/job-detail.html"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_SOURCE_MODES = {
    "0": ("SOCIAL", "社会招聘"),
    "1": ("INTERNSHIP", "实习招聘"),
    "2": ("OTHER", "其他招聘"),
}


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(payload, dict)
        or payload.get("code") != 200
        or not isinstance(payload.get("data"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload


def _source(source_url: str) -> tuple[int, str, str]:
    parsed = urlsplit(source_url)
    work_types = parse_qs(parsed.query).get("workType", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "hr.163.com"
        or parsed.path != _SOURCE_PATH
        or len(work_types) != 1
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    try:
        recruitment_type, plan = _SOURCE_MODES[work_types[0]]
    except KeyError:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1") from None
    return int(work_types[0]), recruitment_type, plan


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _job(row: object, *, recruitment_type: str, plan: str):
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("id")
    title = row.get("name")
    if (
        isinstance(job_id, bool)
        or not isinstance(job_id, int | str)
        or not str(job_id).strip()
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    locations = row.get("workPlaceNameList") or []
    if not isinstance(locations, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    city_labels = tuple(
        dict.fromkeys(
            value.strip()
            for value in locations
            if isinstance(value, str) and value.strip()
        )
    )
    category = row.get("firstPostTypeName")
    category_labels = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=f"https://hr.163.com{_DETAIL_PATH}?{urlencode({'id': job_id})}",
        recruitment_type=recruitment_type,
        plan=plan,
        location_text="、".join(city_labels) or "未公开",
        category_labels=category_labels,
        city_labels=city_labels,
        cohort_labels=_cohorts(
            title,
            row.get("requirement"),
            row.get("description"),
        ),
        published_at=published_at_from_mapping(row),
    )


class NeteaseHrAdapter:
    key = "netease-hr-v1"
    browser_required = False
    authoritative_listing = True

    def check_opportunity(
        self,
        *,
        source_url: str,
        target_url: str,
        config: Mapping[str, object],
        client: FetchClient,
    ) -> SafeHttpResult:
        del config
        _source(source_url)
        target = urlsplit(target_url)
        job_ids = parse_qs(target.query).get("id", ())
        if (
            target.scheme != "https"
            or target.hostname != "hr.163.com"
            or target.path != _DETAIL_PATH
            or len(job_ids) != 1
            or not job_ids[0]
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        response = client.get(f"{_API}/query?{urlencode({'id': job_ids[0]})}")
        payload = _json(response)
        if str(payload["data"].get("id") or "") != job_ids[0]:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        return response

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
        work_type, recruitment_type, plan = _source(source_url)
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

        opportunities = []
        page = 1
        page_size = 10
        truncated = False
        while True:
            heartbeat()
            payload = _json(
                client.post_json(
                    f"{_API}/queryPage",
                    {
                        "currentPage": page,
                        "pageSize": page_size,
                        "workType": work_type,
                    },
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            )
            data = payload["data"]
            rows = data.get("list")
            pages = data.get("pages")
            total = data.get("total")
            if (
                not isinstance(rows, list)
                or isinstance(pages, bool)
                or not isinstance(pages, int)
                or pages < 0
                or isinstance(total, bool)
                or not isinstance(total, int)
                or total < 0
                or (total > 0 and pages < 1)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            opportunities.extend(
                _job(row, recruitment_type=recruitment_type, plan=plan) for row in rows
            )
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if page >= pages or len(opportunities) >= total:
                break
            if len(opportunities) == max_opportunities or page >= max_pages:
                truncated = True
                break
            page += 1

        if not truncated and len(opportunities) != total:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")

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
            pages_read=page,
            truncated=truncated,
        )


NETEASE_HR_ADAPTER = NeteaseHrAdapter()

__all__ = ["NETEASE_HR_ADAPTER", "NeteaseHrAdapter"]
