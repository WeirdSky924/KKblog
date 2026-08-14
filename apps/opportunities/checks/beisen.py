from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_GLOBAL_START = re.compile(rb"\bBSGlobal\s*=\s*")
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_GRADUATION_YEAR_AFTER = re.compile(
    r"毕业(?:时间|日期|年份)?[^。；;\n]{0,16}?(20\d{2})\s*年"
)
_GRADUATION_YEAR_BEFORE = re.compile(
    r"(?<!\d)(20\d{2})\s*年[^。；;\n]{0,20}?(?:毕业|应届)"
)
_CATEGORY_BY_PATH = {"campus": "2", "intern": "3", "social": "1"}
_RECRUITMENT_TYPE = {
    "campus": "CAMPUS",
    "intern": "INTERNSHIP",
    "social": "SOCIAL",
}
_PLAN = {
    "campus": "校园招聘",
    "intern": "实习招聘",
    "social": "社会招聘",
}
_KIND_BY_CATEGORY = {"1": "social", "2": "campus", "3": "intern"}


def _json_object(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not isinstance(value, dict) or value.get("Code") != 200:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return value


def _global_config(body: bytes) -> Mapping[str, object]:
    match = _GLOBAL_START.search(body)
    if match is None:
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
    try:
        text = body[match.end() :].decode("utf-8", errors="strict")
        config, _offset = json.JSONDecoder().raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1") from None
    if not isinstance(config, dict):
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
    return config


def _source_kind(source_url: str) -> str:
    parts = [part for part in urlsplit(source_url).path.split("/") if part]
    return parts[0].casefold() if parts else "jobs"


def _page(
    config: Mapping[str, object], *, category: str | None
) -> Mapping[str, object]:
    pages = config.get("Pages")
    if not isinstance(pages, list):
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
    for page in pages:
        if isinstance(page, dict) and (
            (category is None and page.get("PageType") == 5)
            or (
                category is not None
                and page.get("PageType") == 2
                and str(page.get("BusinessType") or "") == category
            )
        ):
            return page
    raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")


def _display_filters(page: Mapping[str, object]) -> tuple[str, ...]:
    raw = page.get("Config") or "{}"
    try:
        config = json.loads(raw) if isinstance(raw, str) else raw
        items = config["extraBusinessSetting"]["JobAdListSetting"]["FilterItems"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return ("LocId", "ClassificationOne")
    values = []
    for item in items if isinstance(items, list) else ():
        if isinstance(item, dict) and isinstance(item.get("Key"), str):
            values.append(item["Key"])
    return tuple(dict.fromkeys(values)) or ("LocId", "ClassificationOne")


def _option_labels(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    sections = payload.get("Data")
    if not isinstance(sections, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    labels = []
    for section in sections:
        if not isinstance(section, dict) or section.get("Value") != field:
            continue
        for item in section.get("Data") or ():
            if isinstance(item, dict) and isinstance(item.get("Text"), str):
                value = item["Text"].strip()
                if value:
                    labels.append(value)
    return tuple(dict.fromkeys(labels))


def _cohorts(*values: object) -> tuple[str, ...]:
    result = []
    for value in values:
        if isinstance(value, str):
            result.extend(f"20{year}届" for year in _COHORT.findall(value))
            result.extend(f"{year}届" for year in _GRADUATION_YEAR_AFTER.findall(value))
            result.extend(
                f"{year}届" for year in _GRADUATION_YEAR_BEFORE.findall(value)
            )
    return tuple(dict.fromkeys(result))


def _detail_url(source_url: str, job_id: object, job_kind: str) -> str:
    parsed = urlsplit(source_url)
    prefix = job_kind if job_kind in _CATEGORY_BY_PATH else ""
    path = f"/{prefix}/detail" if prefix else "/detail"
    return urlunsplit(("https", parsed.netloc, path, f"jobAdId={job_id}", ""))


def _job(
    row: object,
    *,
    source_url: str,
    source_kind: str,
) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    title = row.get("JobAdName")
    job_id = row.get("JobAdId")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(job_id, int | str)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    locations = row.get("LocNames") or ()
    if not isinstance(locations, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    location_labels = tuple(
        value.strip() for value in locations if isinstance(value, str) and value.strip()
    )
    city_labels = tuple(
        city.strip()
        for value in location_labels
        for city in value.split("·")[-1].split("/")
        if city.strip()
    )
    city = row.get("ClassificationTwo")
    if not city_labels and isinstance(city, str) and city.strip():
        city_labels = (city.strip(),)
    category = row.get("ClassificationOne")
    category_labels = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    cohorts = _cohorts(title, row.get("Require"), row.get("Duty"))
    job_kind = (
        _KIND_BY_CATEGORY.get(str(row.get("CategoryId") or ""), "jobs")
        if source_kind == "jobs"
        else source_kind
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=_detail_url(source_url, job_id, job_kind),
        recruitment_type=_RECRUITMENT_TYPE.get(job_kind, "OTHER"),
        plan=_PLAN.get(job_kind, "官方招聘"),
        location_text="、".join(location_labels) or "未公开",
        category_labels=category_labels,
        city_labels=city_labels,
        cohort_labels=cohorts,
    )


class BeisenZhiyeAdapter:
    key = "beisen-zhiye-v1"
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
        if initial_response.truncated:
            raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
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
        source_kind = _source_kind(source_url)
        category = _CATEGORY_BY_PATH.get(source_kind)
        global_config = _global_config(initial_response.body)
        page = _page(global_config, category=category)
        base = urlunsplit(urlsplit(source_url)._replace(path="", query="", fragment=""))
        filters = _display_filters(page)
        heartbeat()
        conditions_request = {
            "PageId": str(page.get("Key") or ""),
            "displayFilters": list(filters),
        }
        if category is not None:
            conditions_request["Category"] = [category]
        conditions = _json_object(
            client.post_json(
                f"{base}/api/Jobad/GetJobAdSearchConditions",
                conditions_request,
            )
        )
        category_labels = _option_labels(conditions, "ClassificationOne")
        city_labels = _option_labels(conditions, "LocId")

        opportunities = []
        page_index = 0
        page_size = 5
        truncated = False
        while True:
            heartbeat()
            jobs_request = {
                "PageIndex": page_index,
                "PageSize": page_size,
                "KeyWords": "",
                "SpecialType": 0,
                "PortalId": "",
                "DisplayFields": [
                    "Category",
                    "Kind",
                    "LocId",
                    "ClassificationOne",
                    "ClassificationTwo",
                    "Degree",
                    "Salary",
                ],
            }
            if category is not None:
                jobs_request["Category"] = [category]
            payload = _json_object(
                client.post_json(
                    f"{base}/api/Jobad/GetJobAdPageList",
                    jobs_request,
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            )
            rows = payload.get("Data")
            if not isinstance(rows, list):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            opportunities.extend(
                _job(row, source_url=source_url, source_kind=source_kind)
                for row in rows
            )
            total = payload.get("Count")
            if not isinstance(total, int) or total < 0:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if not rows or len(opportunities) >= total:
                break
            if len(opportunities) == max_opportunities or page_index + 1 >= max_pages:
                truncated = True
                break
            page_index += 1
        all_categories = tuple(
            dict.fromkeys(
                (
                    *category_labels,
                    *(label for row in opportunities for label in row.category_labels),
                )
            )
        )
        all_cities = tuple(
            dict.fromkeys(
                (
                    *city_labels,
                    *(label for row in opportunities for label in row.city_labels),
                )
            )
        )
        all_cohorts = tuple(
            dict.fromkeys(label for row in opportunities for label in row.cohort_labels)
        )
        return AdapterResult(
            complete=not truncated,
            opportunities=tuple(opportunities),
            category_labels=all_categories,
            city_labels=all_cities,
            cohort_labels=all_cohorts,
            pages_read=max(1, page_index + 1),
            truncated=truncated,
        )


BEISEN_ZHIYE_ADAPTER = BeisenZhiyeAdapter()

__all__ = ["BEISEN_ZHIYE_ADAPTER", "BeisenZhiyeAdapter"]
