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

_API = "https://campus.game.163.com/api/campuspc"
_SOURCE_PATH = "/app/job/position"
_PROJECT_ID = "102"
_EXPECTED_PROJECT_NAME = "网易互娱2027届校园招聘"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_CITY_SEPARATOR = re.compile(r"[,，、;；]")


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    project_ids = parse_qs(parsed.query).get("id", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "campus.game.163.com"
        or parsed.path != _SOURCE_PATH
        or project_ids != [_PROJECT_ID]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _json(response: SafeHttpResult) -> object:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not isinstance(payload, dict) or payload.get("code") != 200:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload.get("data")


def _project_name(response: SafeHttpResult) -> str:
    rows = _json(response)
    if not isinstance(rows, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("projectId") or "") == _PROJECT_ID
    ]
    if len(matches) != 1 or matches[0].get("projectName") != _EXPECTED_PROJECT_NAME:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return _EXPECTED_PROJECT_NAME


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


def _job(row: object, *, project_name: str) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("id")
    title = row.get("positionName")
    if (
        isinstance(job_id, bool)
        or not isinstance(job_id, int | str)
        or not str(job_id).strip()
        or str(row.get("projectId") or "") != _PROJECT_ID
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    category = row.get("positionTypeName")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    cities = _cities(row.get("workPlaceName"))
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            "https://campus.game.163.com/app/detail/index?"
            f"{urlencode({'id': job_id, 'projectId': _PROJECT_ID})}"
        ),
        recruitment_type="CAMPUS",
        plan=project_name,
        location_text="、".join(cities) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=_cohorts(
            project_name,
            title,
            row.get("positionDescription"),
            row.get("positionRequirement"),
        ),
        published_at=published_at_from_mapping(row),
    )


class NeteaseGameAdapter:
    key = "netease-game-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        _source(source_url)
        return f"{_API}/hy/project/queryOpenList"

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

        project_name = _project_name(initial_response)
        opportunities = []
        page = 1
        page_size = 50
        total = None
        pages = None
        truncated = False
        while True:
            heartbeat()
            url = f"{_API}/position/getJobList?{urlencode({'projectId': _PROJECT_ID, 'currentPage': page, 'pageSize': page_size})}"
            data = _json(client.get(url, max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES))
            if not isinstance(data, dict):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            rows = data.get("list")
            current_total = data.get("total")
            current_pages = data.get("pages")
            if (
                not isinstance(rows, list)
                or isinstance(current_total, bool)
                or not isinstance(current_total, int)
                or current_total < 0
                or isinstance(current_pages, bool)
                or not isinstance(current_pages, int)
                or current_pages < 0
                or (current_total > 0 and current_pages < 1)
                or (total is not None and current_total != total)
                or (pages is not None and current_pages != pages)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = current_total
            pages = current_pages
            opportunities.extend(_job(row, project_name=project_name) for row in rows)
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


NETEASE_GAME_ADAPTER = NeteaseGameAdapter()

__all__ = ["NETEASE_GAME_ADAPTER", "NeteaseGameAdapter"]
