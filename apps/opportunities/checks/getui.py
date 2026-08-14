from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import SafeHttpResult, SafeRequestError

_API = "https://job.getui.com/data/recruit/school/2021/job/list"
_SOURCE_PATH = re.compile(r"/campus/position/(\d+)\Z")
_SOURCE_ANCHORS = {"226": "算法类", "192": "技术类"}
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _source(source_url: str) -> tuple[str, str]:
    parsed = urlsplit(source_url)
    match = _SOURCE_PATH.fullmatch(parsed.path)
    categories = parse_qs(parsed.query).get("type", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "job.getui.com"
        or match is None
        or len(categories) != 1
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    anchor = match.group(1)
    category = categories[0].strip()
    if _SOURCE_ANCHORS.get(anchor) != category:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    return anchor, category


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(payload, dict)
        or payload.get("errNo") != 0
        or not isinstance(payload.get("data"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload["data"]


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        dict.fromkeys(
            label.strip() for label in re.split(r"[/,，、]", value) if label.strip()
        )
    )


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _job(row: object, *, category: str) -> tuple[str, CollectedOpportunity]:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("id")
    title = row.get("name")
    row_category = row.get("type")
    if (
        isinstance(job_id, bool)
        or not isinstance(job_id, int | str)
        or not str(job_id).strip()
        or not isinstance(title, str)
        or not title.strip()
        or row_category != category
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = _labels(row.get("city"))
    internship = "实习" in title
    return str(job_id).strip(), CollectedOpportunity(
        title=title.strip(),
        target_url=(
            f"https://job.getui.com/campus/position/{str(job_id).strip()}?"
            f"{urlencode({'type': category})}"
        ),
        recruitment_type="INTERNSHIP" if internship else "CAMPUS",
        plan="实习招聘" if internship else "校园招聘",
        location_text="、".join(cities) or "未公开",
        category_labels=(category,),
        city_labels=cities,
        cohort_labels=_cohorts(title, row.get("content"), row.get("require")),
    )


class GetuiAdapter:
    key = "getui-v1"
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
        anchor, category = _source(source_url)
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
        rows = []
        total = None
        truncated = False
        while True:
            heartbeat()
            data = _json(
                client.post_json(
                    _API,
                    {
                        "pageNum": page,
                        "pageSize": page_size,
                        "typeList": [category],
                    },
                )
            )
            batch = data.get("list")
            current_total = data.get("total")
            if (
                not isinstance(batch, list)
                or isinstance(current_total, bool)
                or not isinstance(current_total, int)
                or current_total < 0
                or (total is not None and current_total != total)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = current_total
            rows.extend(batch)
            if len(rows) > max_opportunities:
                rows = rows[:max_opportunities]
                truncated = True
                break
            if len(rows) >= total:
                break
            if not batch:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            if len(rows) == max_opportunities or page >= max_pages:
                truncated = True
                break
            page += 1

        parsed = tuple(_job(row, category=category) for row in rows)
        identities = {job_id for job_id, _item in parsed}
        if not truncated and (len(rows) != total or anchor not in identities):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        items = tuple(item for _job_id, item in parsed)
        return AdapterResult(
            complete=not truncated,
            opportunities=items,
            category_labels=(category,),
            city_labels=tuple(
                dict.fromkeys(label for item in items for label in item.city_labels)
            ),
            cohort_labels=tuple(
                dict.fromkeys(label for item in items for label in item.cohort_labels)
            ),
            pages_read=page,
            truncated=truncated,
        )


GETUI_ADAPTER = GetuiAdapter()

__all__ = ["GETUI_ADAPTER", "GetuiAdapter"]
