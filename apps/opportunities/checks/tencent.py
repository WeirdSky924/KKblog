from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = "https://join.qq.com/api/v1/position/searchPosition"
_SOURCE_PATH = "/post.html"
_PROJECT_MAPPING_ID = 2
_CATEGORY_LABELS = {
    2: "技术类",
    3: "产品类",
    4: "设计类",
    5: "市场类",
    6: "职能类",
    7: "专项人才类",
}


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "join.qq.com"
        or parsed.path != _SOURCE_PATH
        or parse_qs(parsed.query).get("query") != ["p_2"]
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
        or payload.get("status") != 0
        or not isinstance(payload.get("data"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload["data"]


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    post_id = row.get("postId")
    title = row.get("positionTitle")
    project_id = row.get("projectId")
    family_id = row.get("positionFamily")
    if (
        not isinstance(post_id, str)
        or not post_id.isdigit()
        or not isinstance(title, str)
        or not title.strip()
        or project_id != _PROJECT_MAPPING_ID
        or (family_id is not None and family_id not in _CATEGORY_LABELS)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities_value = row.get("workCities")
    cities = (
        tuple(dict.fromkeys(cities_value.split()))
        if isinstance(cities_value, str)
        else ()
    )
    project = row.get("projectName") or row.get("recruitLabelName")
    plan = (
        project.strip() if isinstance(project, str) and project.strip() else "应届实习"
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            f"https://join.qq.com/post_detail.html?{urlencode({'postid': post_id})}"
        ),
        recruitment_type="INTERNSHIP",
        plan=plan,
        location_text="、".join(cities) or "未公开",
        category_labels=(
            (_CATEGORY_LABELS[family_id],) if family_id is not None else ()
        ),
        city_labels=cities,
        cohort_labels=(),
    )


def _request(page: int, page_size: int) -> dict[str, object]:
    return {
        "projectIdList": [],
        "projectMappingIdList": [_PROJECT_MAPPING_ID],
        "keyword": "",
        "bgList": [],
        "workCountryType": 0,
        "workCityList": [],
        "recruitCityList": [],
        "positionFidList": [],
        "pageIndex": page,
        "pageSize": page_size,
    }


class TencentAdapter:
    key = "tencent-v1"
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
        page_size = 100
        total = None
        opportunities = []
        truncated = False
        while True:
            heartbeat()
            data = _json(
                client.post_json(
                    _API,
                    _request(page, page_size),
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            )
            rows = data.get("positionList")
            current_total = data.get("count")
            if (
                not isinstance(rows, list)
                or isinstance(current_total, bool)
                or not isinstance(current_total, int)
                or current_total < 0
                or (total is not None and current_total != total)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = current_total
            opportunities.extend(_job(row) for row in rows)
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if len(opportunities) >= total:
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


TENCENT_ADAPTER = TencentAdapter()

__all__ = ["TENCENT_ADAPTER", "TencentAdapter"]
