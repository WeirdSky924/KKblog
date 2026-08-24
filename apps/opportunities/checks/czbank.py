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

_SOURCE_PATH = "/zpweb/planController/gotoIndex.mvc"
_API = "https://zp.czbank.com.cn/zpweb/planController/getPost.mvc"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    page_types = parse_qs(parsed.query).get("pageType", ())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "zp.czbank.com.cn"
        or parsed.path != _SOURCE_PATH
        or page_types != ["1"]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _payload(response: SafeHttpResult) -> tuple[list[object], int]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("gb18030"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    body = payload.get("body") if isinstance(payload, dict) else None
    page = body[0] if isinstance(body, list) and len(body) == 1 else None
    if (
        not isinstance(payload, dict)
        or payload.get("code") not in (1, "1")
        or not isinstance(page, dict)
        or not isinstance(page.get("dataList"), list)
        or isinstance(page.get("postTotalPage"), bool)
        or not isinstance(page.get("postTotalPage"), int)
        or page["postTotalPage"] < 0
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return page["dataList"], page["postTotalPage"]


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        dict.fromkeys(
            label.strip() for label in re.split(r"[,，、/;；]", value) if label.strip()
        )
    )


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _job(row: object) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("postId")
    title = row.get("name")
    view_options = row.get("vo")
    if (
        not isinstance(job_id, str | int)
        or not str(job_id).strip()
        or not isinstance(title, str)
        or not title.strip()
        or not isinstance(view_options, dict)
        or view_options.get("needPost") != "04"
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = _labels(row.get("locationName"))
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            "https://zp.czbank.com.cn/zpweb/zpPostController/"
            f"jobDetailPage.mvc?{urlencode({'postId': str(job_id).strip()})}"
        ),
        recruitment_type="CAMPUS",
        plan="校园招聘",
        location_text="、".join(cities) or "未公开",
        category_labels=(),
        city_labels=cities,
        cohort_labels=_cohorts(title, row.get("majorCond")),
        published_at=published_at_from_mapping(row),
    )


class CzbankAdapter:
    key = "czbank-v1"
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
        page_size = 6
        total_pages = None
        opportunities = []
        truncated = False
        while True:
            heartbeat()
            query = urlencode(
                {
                    "zpType": "1",
                    "start": (page - 1) * page_size,
                    "end": page * page_size,
                    "depid": "",
                    "educ": "",
                    "orgId": "",
                    "postName": "",
                    "location": "",
                }
            )
            rows, current_total_pages = _payload(
                client.get(f"{_API}?{query}", max_response_bytes=MAX_RESPONSE_BYTES)
            )
            if (
                (total_pages is not None and total_pages != current_total_pages)
                or (current_total_pages == 0 and rows)
                or (current_total_pages > 0 and page > current_total_pages)
                or len(rows) > page_size
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total_pages = current_total_pages
            opportunities.extend(_job(row) for row in rows)
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if page >= total_pages:
                break
            if not rows:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            if len(opportunities) == max_opportunities or page >= max_pages:
                truncated = True
                break
            page += 1

        items = tuple(opportunities)
        return AdapterResult(
            complete=not truncated,
            opportunities=items,
            category_labels=(),
            city_labels=tuple(
                dict.fromkeys(label for item in items for label in item.city_labels)
            ),
            cohort_labels=tuple(
                dict.fromkeys(label for item in items for label in item.cohort_labels)
            ),
            pages_read=max(1, page),
            truncated=truncated,
        )


CZBANK_ADAPTER = CzbankAdapter()

__all__ = ["CZBANK_ADAPTER", "CzbankAdapter"]
