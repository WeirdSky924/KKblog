from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = "https://zhaopin.meituan.com/api/official/job/getJobList"
_SOURCE_PATH = "/web/position"
_HIRING_TYPE = "4_1"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    hiring_types = parse_qs(parsed.query).get("hiringType", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "zhaopin.meituan.com"
        or parsed.path != _SOURCE_PATH
        or hiring_types != [_HIRING_TYPE]
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
        or payload.get("message") != "成功"
        or not isinstance(payload.get("data"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload["data"]


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _cities(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = []
    for row in value:
        name = row.get("name") if isinstance(row, dict) else None
        if isinstance(name, str) and name.strip():
            cities.append(name.strip())
    return tuple(dict.fromkeys(cities))


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("jobUnionId")
    title = row.get("name")
    if (
        not isinstance(job_id, str)
        or not job_id.strip()
        or not isinstance(title, str)
        or not title.strip()
        or str(row.get("jobType") or "") != "1"
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = _cities(row.get("cityList"))
    category = row.get("jobFamilyGroup") or row.get("jobFamily")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    project_name = row.get("projectName")
    plan = (
        project_name.strip()
        if isinstance(project_name, str) and project_name.strip()
        else "校园招聘"
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            "https://zhaopin.meituan.com/web/position/detail?"
            f"{urlencode({'jobUnionId': job_id.strip(), 'highlightType': 'campus'})}"
        ),
        recruitment_type="CAMPUS",
        plan=plan,
        location_text="、".join(cities) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=_cohorts(
            plan,
            title,
            row.get("jobDuty"),
            row.get("jobRequirement"),
        ),
    )


def _request(page: int, page_size: int) -> dict[str, object]:
    return {
        "page": {"pageNo": page, "pageSize": page_size},
        "jobShareType": "1",
        "keywords": "",
        "cityList": [],
        "department": [],
        "jfJgList": [],
        "jobType": [{"code": "4", "subCode": ["1"]}],
        "typeCode": ["1"],
        "specialCode": [],
    }


class MeituanAdapter:
    key = "meituan-v1"
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
        page_size = 5
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
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            )
            rows = data.get("list")
            pagination = data.get("page")
            current_page = (
                pagination.get("pageNo") if isinstance(pagination, dict) else None
            )
            current_size = (
                pagination.get("pageSize") if isinstance(pagination, dict) else None
            )
            current_pages = (
                pagination.get("totalPage") if isinstance(pagination, dict) else None
            )
            current_total = (
                pagination.get("totalCount") if isinstance(pagination, dict) else None
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
            identity = (item.target_url, item.title.casefold())
            current = unique.get(identity)
            if current is not None and current != item:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            unique[identity] = item
        opportunities = list(unique.values())
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


MEITUAN_ADAPTER = MeituanAdapter()

__all__ = ["MEITUAN_ADAPTER", "MeituanAdapter"]
