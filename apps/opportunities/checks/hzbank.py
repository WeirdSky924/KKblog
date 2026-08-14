from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlencode, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = "https://myjob.hzbank.com.cn/hzzp-apply/employInfo/queryEmployInfosList"
_SOURCE_PATH = "/hzzp-apply-web/static/index.html"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_SOURCE_MODES = {
    "/employ/school": ("01", "CAMPUS", "校园招聘"),
    "/employ/ungraduate": ("03", "INTERNSHIP", "实习招聘"),
}
_CATEGORY_LABELS = {
    "1": "管理",
    "2": "营销",
    "3": "运营/支持",
    "4": "科技",
    "5": "产品",
    "6": "风险",
    "7": "交易",
    "8": "职能",
}


def _source(source_url: str) -> tuple[str, str, str]:
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "myjob.hzbank.com.cn"
        or parsed.path != _SOURCE_PATH
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    try:
        return _SOURCE_MODES[parsed.fragment.rstrip("/")]
    except KeyError:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1") from None


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(payload, dict)
        or payload.get("errorCode") != "0"
        or not isinstance(payload.get("result"), dict)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload["result"]


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        dict.fromkeys(
            label.strip() for label in re.split(r"[,，、/]", value) if label.strip()
        )
    )


def _cohorts(*values: object) -> tuple[str, ...]:
    labels = []
    for value in values:
        if isinstance(value, str):
            labels.extend(f"20{year}届" for year in _COHORT.findall(value))
    return tuple(dict.fromkeys(labels))


def _category(row: Mapping[str, object]) -> tuple[str, ...]:
    for field in ("positionCategoryName", "positionCategorys"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return (value.strip(),)
    value = row.get("positionCategory")
    label = _CATEGORY_LABELS.get(str(value or ""))
    return (label,) if label else ()


def _job(
    row: object,
    *,
    recruitment_type: str,
    plan: str,
) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("id")
    title = row.get("positionName")
    if (
        not isinstance(job_id, str | int)
        or not str(job_id).strip()
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = _labels(row.get("workSpace"))
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            "https://myjob.hzbank.com.cn/hzzp-apply-web/static/"
            f"index.html#/employDesc/{str(job_id).strip()}"
        ),
        recruitment_type=recruitment_type,
        plan=plan,
        location_text="、".join(cities) or "未公开",
        category_labels=_category(row),
        city_labels=cities,
        cohort_labels=_cohorts(
            title,
            row.get("jobDesc"),
            row.get("jobRequire"),
        ),
    )


class HzbankAdapter:
    key = "hzbank-v1"
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
        position_type, recruitment_type, plan = _source(source_url)
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

        opportunities = []
        page = 0
        page_size = 20
        truncated = False
        while True:
            heartbeat()
            result = _json(
                client.get(
                    f"{_API}?"
                    + urlencode(
                        {
                            "page": page,
                            "positionName": "",
                            "positionType": position_type,
                            "size": page_size,
                            "organNo": "",
                            "batchNos": "",
                            "positionCategorys": "",
                        }
                    ),
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            )
            rows = result.get("content")
            total = result.get("totalElements")
            pages = result.get("totalPages")
            number = result.get("number")
            if (
                not isinstance(rows, list)
                or isinstance(total, bool)
                or not isinstance(total, int)
                or total < 0
                or isinstance(pages, bool)
                or not isinstance(pages, int)
                or pages < 0
                or number != page
                or (total > 0 and pages < 1)
            ):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            opportunities.extend(
                _job(row, recruitment_type=recruitment_type, plan=plan) for row in rows
            )
            if len(opportunities) > max_opportunities:
                opportunities = opportunities[:max_opportunities]
                truncated = True
                break
            if page + 1 >= pages or len(opportunities) >= total:
                break
            if len(opportunities) == max_opportunities or page + 1 >= max_pages:
                truncated = True
                break
            page += 1

        if not truncated and len(opportunities) != total:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        items = tuple(opportunities)
        return AdapterResult(
            complete=not truncated,
            opportunities=items,
            category_labels=tuple(
                dict.fromkeys(label for item in items for label in item.category_labels)
            ),
            city_labels=tuple(
                dict.fromkeys(label for item in items for label in item.city_labels)
            ),
            cohort_labels=tuple(
                dict.fromkeys(label for item in items for label in item.cohort_labels)
            ),
            pages_read=max(1, page + 1),
            truncated=truncated,
        )


HZBANK_ADAPTER = HzbankAdapter()

__all__ = ["HZBANK_ADAPTER", "HzbankAdapter"]
