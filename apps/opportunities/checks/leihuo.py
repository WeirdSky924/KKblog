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
from .http import SafeHttpResult, SafeRequestError

_API = "https://xiaozhao.leihuo.netease.com/api"
_PROJECTS = {
    "full": ("77", "CAMPUS", "27届校园招聘"),
}
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != 200
        or not isinstance(payload.get("data"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload


def _source(source_url: str):
    parsed = urlsplit(source_url)
    if parsed.hostname != "leihuo.163.com" or parsed.path != "/campus/":
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    route = parsed.fragment.removeprefix("/").partition("?")[0]
    try:
        project_id, recruitment_type, plan = _PROJECTS[route]
    except KeyError:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1") from None
    return project_id, recruitment_type, plan


def _api_url(path: str, params: Mapping[str, object]) -> str:
    return f"{_API}/{path}?{urlencode(params, doseq=True)}"


def _filter_labels(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    simple = payload["data"].get("simple")
    section = simple.get(key) if isinstance(simple, dict) else None
    rows = section.get("data") if isinstance(section, dict) else None
    if not isinstance(rows, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    labels = []
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if isinstance(name, str) and name.strip():
            labels.append(name.strip())
    return tuple(dict.fromkeys(labels))


def _cohorts(*values: object) -> tuple[str, ...]:
    result = []
    for value in values:
        if isinstance(value, str):
            result.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(result))


def _job(row: object, *, recruitment_type: str, plan: str):
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    title = row.get("job_name")
    target_url = row.get("job_detail_url")
    job_id = row.get("ehr_job_id")
    project_id = row.get("ehr_project_id")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(target_url, str)
        or not isinstance(job_id, str | int)
        or not isinstance(project_id, str | int)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    parsed = urlsplit(target_url)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "campus.163.com"
        or parsed.path != "/app/detail/index"
        or query.get("id") != [str(job_id)]
        or query.get("projectId") != [str(project_id)]
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    location = row.get("work_place_name")
    category = row.get("category_name")
    if not isinstance(location, str) or not location.strip():
        location = "未公开"
    if not isinstance(category, str):
        category = ""
    cohorts = _cohorts(row.get("job_target"), row.get("target"), title)
    return CollectedOpportunity(
        title=title.strip(),
        target_url=target_url,
        recruitment_type=recruitment_type,
        plan=plan,
        location_text=location.strip(),
        category_labels=(category.strip(),) if category.strip() else (),
        city_labels=(location.strip(),) if location != "未公开" else (),
        cohort_labels=cohorts,
        published_at=published_at_from_mapping(row),
    )


class NeteaseLeihuoAdapter:
    key = "netease-leihuo-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        project_id, _recruitment_type, _plan = _source(source_url)
        return _api_url("apply/job/filter/show", {"project_id": project_id})

    def check_opportunity(
        self,
        *,
        source_url: str,
        target_url: str,
        config: Mapping[str, object],
        client: FetchClient,
    ) -> SafeHttpResult:
        del config
        project_id, _recruitment_type, _plan = _source(source_url)
        parsed = urlsplit(target_url)
        query = parse_qs(parsed.query)
        if (
            parsed.hostname != "campus.163.com"
            or parsed.path != "/app/detail/index"
            or len(query.get("id", ())) != 1
            or query.get("projectId") != [project_id]
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        job_id = query["id"][0]
        response = client.get(
            _api_url(
                "apply/job/detail/show",
                {"job_id": job_id, "project_id": project_id},
            )
        )
        payload = _json(response)
        data = payload["data"]
        if str(data.get("ehr_job_id") or data.get("job_id") or "") != job_id:
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
        project_id, recruitment_type, plan = _source(source_url)
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
        heartbeat()
        filters = _json(client.get(self.source_probe_url(source_url)))
        city_labels = _filter_labels(filters, "job_apply_work_place")
        category_labels = _filter_labels(filters, "job_apply_category")

        opportunities = []
        page = 1
        page_size = 10
        truncated = False
        while True:
            heartbeat()
            payload = _json(
                client.get(
                    _api_url(
                        "apply/job/list/show",
                        {
                            "project_id": project_id,
                            "page_size": page_size,
                            "page_number": page,
                            "job_name": "",
                        },
                    )
                )
            )
            data = payload["data"]
            rows = data.get("apply_job_list")
            total = data.get("count_number")
            pages_count = data.get("pages_count")
            last_page = data.get("last_page")
            if (
                not isinstance(rows, list)
                or not isinstance(total, int)
                or total < 0
                or isinstance(pages_count, bool)
                or not isinstance(pages_count, int)
                or pages_count < 1
                or not isinstance(last_page, bool)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            opportunities.extend(
                _job(row, recruitment_type=recruitment_type, plan=plan) for row in rows
            )
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if last_page or page >= pages_count or len(opportunities) >= total:
                break
            if len(opportunities) == max_opportunities or page >= max_pages:
                truncated = True
                break
            page += 1
        all_categories = tuple(
            dict.fromkeys(
                (
                    *category_labels,
                    *(
                        label
                        for item in opportunities
                        for label in item.category_labels
                    ),
                )
            )
        )
        all_cities = tuple(
            dict.fromkeys(
                (
                    *city_labels,
                    *(label for item in opportunities for label in item.city_labels),
                )
            )
        )
        cohorts = tuple(
            dict.fromkeys(
                label for item in opportunities for label in item.cohort_labels
            )
        )
        return AdapterResult(
            complete=not truncated,
            opportunities=tuple(opportunities),
            category_labels=all_categories,
            city_labels=all_cities,
            cohort_labels=cohorts,
            pages_read=page,
            truncated=truncated,
        )


NETEASE_LEIHUO_ADAPTER = NeteaseLeihuoAdapter()

__all__ = ["NETEASE_LEIHUO_ADAPTER", "NeteaseLeihuoAdapter"]
