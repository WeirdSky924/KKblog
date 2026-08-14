from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import (
    MAX_ADAPTER_RESPONSE_BYTES,
    MAX_RESPONSE_BYTES,
    SafeHttpResult,
    SafeRequestError,
)

_API_ROOT = "https://hrcareersweb.antgroup.com/api"
_CONDITIONS_API = f"{_API_ROOT}/searchCondition/list?ctoken=bigfish_ctoken_1ac62hicbh"
_POSITIONS_API = f"{_API_ROOT}/campus/position/search?ctoken=bigfish_ctoken_1ac62hicbh"
_SOURCE_PATH = "/campus-full-list"
_SOURCE_TYPE = "campus_graduates"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "talent.antgroup.com"
        or parsed.path != _SOURCE_PATH
        or parse_qs(parsed.query).get("type") != [_SOURCE_TYPE]
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


def _batch_ids(payload: Mapping[str, object]) -> tuple[str, ...]:
    content = payload.get("content")
    search_items = content.get("searchItems") if isinstance(content, dict) else None
    if not isinstance(search_items, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    groups = [
        row
        for row in search_items
        if isinstance(row, dict) and row.get("type") == "recruitType"
    ]
    if len(groups) != 1 or not isinstance(groups[0].get("items"), list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    graduate_groups = [
        row
        for row in groups[0]["items"]
        if isinstance(row, dict) and row.get("value") == _SOURCE_TYPE
    ]
    if len(graduate_groups) != 1 or not isinstance(
        graduate_groups[0].get("children"), list
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    identities = []
    for row in graduate_groups[0]["children"]:
        value = row.get("value") if isinstance(row, dict) else None
        if not isinstance(value, str) or not value.isdigit():
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        identities.append(value)
    if not identities:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return tuple(dict.fromkeys(identities))


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _job(row: object, *, batch_ids: frozenset[str]) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    identity = row.get("id")
    title = row.get("name")
    batch_id = row.get("batchId")
    if (
        isinstance(identity, bool)
        or not isinstance(identity, int)
        or identity <= 0
        or not isinstance(title, str)
        or not title.strip()
        or str(batch_id) not in batch_ids
        or row.get("batchType") != "graduate"
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    locations = row.get("workLocations")
    if not isinstance(locations, list) or any(
        not isinstance(item, str) for item in locations
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = tuple(dict.fromkeys(item.strip() for item in locations if item.strip()))
    category = row.get("categoryName")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    batch_name = row.get("batchName")
    plan = (
        batch_name.strip()
        if isinstance(batch_name, str) and batch_name.strip()
        else "应届生招聘"
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            "https://talent.antgroup.com/campus-position?"
            f"{urlencode({'positionId': identity})}"
        ),
        recruitment_type="CAMPUS",
        plan=plan,
        location_text="、".join(cities) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=_cohorts(plan),
    )


def _request(
    page: int, page_size: int, batch_ids: tuple[str, ...]
) -> dict[str, object]:
    return {
        "channel": "campus_group_official_site",
        "language": "zh",
        "regions": "",
        "subCategories": "",
        "bgCode": "",
        "pageIndex": page,
        "pageSize": page_size,
        "recruitType": [],
        "batchIds": list(batch_ids),
    }


class AntgroupAdapter:
    key = "antgroup-v1"
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

        heartbeat()
        batch_ids = _batch_ids(
            _json(
                client.post_json(
                    _CONDITIONS_API, {}, max_response_bytes=MAX_RESPONSE_BYTES
                )
            )
        )
        allowed_batches = frozenset(batch_ids)
        page = 1
        page_size = 5
        total = None
        opportunities = []
        truncated = False
        while True:
            heartbeat()
            payload = _json(
                client.post_json(
                    _POSITIONS_API,
                    _request(page, page_size, batch_ids),
                    max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
                )
            )
            rows = payload.get("content")
            current_page = payload.get("currentPage")
            current_size = payload.get("pageSize")
            current_total = payload.get("totalCount")
            if (
                not isinstance(rows, list)
                or current_page != page
                or current_size != page_size
                or isinstance(current_total, bool)
                or not isinstance(current_total, int)
                or current_total < 0
                or (total is not None and current_total != total)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = current_total
            opportunities.extend(_job(row, batch_ids=allowed_batches) for row in rows)
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


ANTGROUP_ADAPTER = AntgroupAdapter()

__all__ = ["ANTGROUP_ADAPTER", "AntgroupAdapter"]
