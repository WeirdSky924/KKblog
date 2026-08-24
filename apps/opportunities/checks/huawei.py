from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import (
    AdapterResult,
    CollectedOpportunity,
    FetchClient,
    published_at_from_mapping,
)
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = (
    "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/"
    "recruitmentPosition/pub/getJobPage?X-HW-ID=app_000000035886"
)
_SOURCE_PATH = "/cn/campus-recruitment-job-list"
_RECRUITMENT_TYPE = "FRESH_GRADUATE"
_HEADERS = {
    "Origin": "https://career.huawei.com",
    "Referer": "https://career.huawei.com/",
    "X-Jalor-TenantAlias": "hcm",
    "X-HW-ID": "app_000000035886",
    "X-Referer": "https://career.huawei.com/cn",
}


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    recruitment_types = parse_qs(parsed.query).get("recruitmentType", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "career.huawei.com"
        or parsed.path != _SOURCE_PATH
        or recruitment_types != [_RECRUITMENT_TYPE]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "SUCCESS"
        or payload.get("errors") is not None
        or not isinstance(payload.get("data"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload["data"]


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        dict.fromkeys(label.strip() for label in value.split("/") if label.strip())
    )


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    advertisement_id = row.get("advertisementId")
    title = row.get("jobName")
    if (
        isinstance(advertisement_id, bool)
        or not isinstance(advertisement_id, int)
        or advertisement_id <= 0
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = _labels(row.get("workPlace"))
    category = row.get("categoryName")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    scenario = row.get("scenarioName")
    plan = (
        scenario.strip() if isinstance(scenario, str) and scenario.strip() else "应届生"
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            "https://career.huawei.com/cn/job-details?"
            f"{urlencode({'advertisementId': advertisement_id})}"
        ),
        recruitment_type="CAMPUS",
        plan=plan,
        location_text="、".join(cities) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=(),
        published_at=published_at_from_mapping(row),
    )


def _request(page: int, page_size: int) -> dict[str, object]:
    return {
        "curPage": page,
        "pageSize": page_size,
        "jobType": "CR",
        "recruitmentType": [_RECRUITMENT_TYPE],
    }


class HuaweiAdapter:
    key = "huawei-v1"
    browser_required = False
    authoritative_listing = True

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

        page = 1
        page_size = 10
        total = None
        pages = None
        opportunities = []
        truncated = False
        while True:
            heartbeat()
            data = _json(
                client.post_json(
                    _API,
                    _request(page, page_size),
                    headers=_HEADERS,
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            )
            pagination = data.get("pageVO")
            rows = data.get("result")
            current_page = (
                pagination.get("curPage") if isinstance(pagination, dict) else None
            )
            current_size = (
                pagination.get("pageSize") if isinstance(pagination, dict) else None
            )
            current_pages = (
                pagination.get("totalPages") if isinstance(pagination, dict) else None
            )
            current_total = (
                pagination.get("totalRows") if isinstance(pagination, dict) else None
            )
            if (
                not isinstance(rows, list)
                or current_page != page
                or current_size != page_size
                or isinstance(current_pages, bool)
                or not isinstance(current_pages, int)
                or current_pages < 0
                or isinstance(current_total, bool)
                or not isinstance(current_total, int)
                or current_total < 0
                or (current_total > 0 and current_pages < 1)
                or (total is not None and current_total != total)
                or (pages is not None and current_pages != pages)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = current_total
            pages = current_pages
            opportunities.extend(_job(row) for row in rows)
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if page >= pages or len(opportunities) >= total:
                break
            if not rows:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            if len(opportunities) == max_opportunities or page >= max_pages:
                truncated = True
                break
            page += 1

        if not truncated and len(opportunities) != total:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        unique = {}
        for item in opportunities:
            if item.target_url in unique:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            unique[item.target_url] = item
        categories = tuple(
            dict.fromkeys(
                label for item in opportunities for label in item.category_labels
            )
        )
        cities = tuple(
            dict.fromkeys(label for item in opportunities for label in item.city_labels)
        )
        return AdapterResult(
            complete=not truncated,
            opportunities=tuple(opportunities),
            category_labels=categories,
            city_labels=cities,
            cohort_labels=(),
            pages_read=page,
            truncated=truncated,
        )


HUAWEI_ADAPTER = HuaweiAdapter()

__all__ = ["HUAWEI_ADAPTER", "HuaweiAdapter"]
