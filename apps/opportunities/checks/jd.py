from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import (
    MAX_ADAPTER_RESPONSE_BYTES,
    MAX_LARGE_ADAPTER_RESPONSE_BYTES,
    SafeHttpResult,
    SafeRequestError,
)

_PROJECTS_API = "https://campus.jd.com/api/wx/position/getProjectList"
_JOBS_API = "https://campus.jd.com/api/wx/position/page?type=present"
_PROJECT_ID = "45"
_PROJECT_NAME = "JD YOUNG-实习生计划"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    route, separator, query = parsed.fragment.removeprefix("/").partition("?")
    project_ids = parse_qs(query).get("selProjects", ()) if separator else ()
    if (
        parsed.scheme != "https"
        or parsed.hostname != "campus.jd.com"
        or parsed.path not in ("", "/")
        or route != "jobs"
        or project_ids != [_PROJECT_ID]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload


def _project(response: SafeHttpResult) -> None:
    body = _json(response).get("body")
    groups = body.get("projectList") if isinstance(body, dict) else None
    if not isinstance(groups, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    matches = []
    for group in groups:
        if not isinstance(group, dict) or group.get("code") != "internship":
            continue
        sections = group.get("groupList")
        if not isinstance(sections, list):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        for section in sections:
            plans = section.get("planMapList") if isinstance(section, dict) else None
            if not isinstance(plans, list):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            matches.extend(
                plan
                for plan in plans
                if isinstance(plan, dict) and str(plan.get("id") or "") == _PROJECT_ID
            )
    if len(matches) != 1 or matches[0].get("planName") != _PROJECT_NAME:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _locations(value: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    displays = []
    cities = []
    for row in value:
        label = row.get("workCity") if isinstance(row, dict) else None
        if not isinstance(label, str) or not label.strip():
            continue
        display = label.strip()
        displays.append(display)
        city = display.rsplit("-", 1)[-1]
        cities.append(city)
    return tuple(dict.fromkeys(displays)), tuple(dict.fromkeys(cities))


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    publish_id = row.get("publishId")
    req_id = row.get("reqId")
    title = row.get("positionName")
    if (
        isinstance(publish_id, bool)
        or not isinstance(publish_id, int | str)
        or not str(publish_id).strip()
        or isinstance(req_id, bool)
        or not isinstance(req_id, int | str)
        or not str(req_id).strip()
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    displays, cities = _locations(row.get("requirementVoList"))
    category = row.get("jobDirection")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=f"https://campus.jd.com/#/details?id={publish_id}",
        recruitment_type="INTERNSHIP",
        plan=_PROJECT_NAME,
        location_text="、".join(displays) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=_cohorts(
            title,
            row.get("workContent"),
            row.get("qualification"),
        ),
    )


def _page_payload(*, page_size: int, page_index: int) -> dict[str, object]:
    return {
        "pageSize": page_size,
        "pageIndex": page_index,
        "parameter": {
            "positionName": "",
            "planIdList": [_PROJECT_ID],
            "jobDirectionCodeList": [],
            "workCityCodeList": [],
            "positionDeptList": [],
        },
    }


def _page_rows(payload: Mapping[str, object]) -> tuple[list[object], int]:
    body = payload.get("body")
    rows = body.get("items") if isinstance(body, dict) else None
    total = body.get("totalNumber") if isinstance(body, dict) else None
    if (
        not isinstance(rows, list)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return rows, total


class JdCampusAdapter:
    key = "jd-campus-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        _source(source_url)
        return _PROJECTS_API

    def collect(
        self,
        *,
        source_url: str,
        config: Mapping[str, object],
        client: FetchClient,
        initial_response: SafeHttpResult,
        heartbeat,
    ) -> AdapterResult:
        _source(source_url)
        _project(initial_response)
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

        page_index = 0
        page_size = 5
        total = None
        opportunities = []
        truncated = False
        requests_read = 0
        while True:
            if requests_read >= max_pages:
                truncated = True
                break
            heartbeat()
            response = client.post_json(
                _JOBS_API,
                _page_payload(page_size=page_size, page_index=page_index),
                max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
            )
            requests_read += 1
            if response.truncated:
                rows = []
                current_total = None
                first_index = page_index * page_size
                for offset in range(page_size):
                    if requests_read >= max_pages:
                        truncated = True
                        break
                    heartbeat()
                    single = _json(
                        client.post_json(
                            _JOBS_API,
                            _page_payload(
                                page_size=1,
                                page_index=first_index + offset,
                            ),
                            max_response_bytes=MAX_LARGE_ADAPTER_RESPONSE_BYTES,
                        )
                    )
                    requests_read += 1
                    single_rows, single_total = _page_rows(single)
                    if len(single_rows) != 1:
                        raise SafeRequestError(
                            "opportunities.adapter_response_invalid.v1"
                        )
                    if current_total is not None and single_total != current_total:
                        raise SafeRequestError(
                            "opportunities.adapter_response_invalid.v1"
                        )
                    current_total = single_total
                    rows.extend(single_rows)
                if truncated:
                    opportunities.extend(_job(row) for row in rows)
                    break
            else:
                rows, current_total = _page_rows(_json(response))
            if total is not None and current_total != total:
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
            if len(opportunities) == max_opportunities:
                truncated = True
                break
            page_index += 1

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
            pages_read=requests_read,
            truncated=truncated,
        )


JD_CAMPUS_ADAPTER = JdCampusAdapter()

__all__ = ["JD_CAMPUS_ADAPTER", "JdCampusAdapter"]
