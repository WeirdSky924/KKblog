from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .adapters import AdapterResult, CollectedOpportunity, FetchClient
from .http import MAX_ADAPTER_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_API = "https://job.dahuatech.com/talent-pool/api/bs-info/list-position-by-search"
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_SOURCE_MODES = {
    ("CampusPosition", "11"): (2, "CAMPUS", "校园招聘", "CampusApply"),
    ("SelfControl", "16"): (3, "INTERNSHIP", "实习招聘", "AdvanceApply"),
}


def _source(source_url: str) -> tuple[int, str, str, str]:
    parsed = urlsplit(source_url)
    fragment = parsed.fragment
    route, separator, query = fragment.removeprefix("/").partition("?")
    source_ids = parse_qs(query).get("id", ()) if separator else ()
    if (
        parsed.scheme != "https"
        or parsed.hostname != "job.dahuatech.com"
        or parsed.path != "/"
        or len(source_ids) != 1
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    try:
        return _SOURCE_MODES[(route, source_ids[0])]
    except KeyError:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1") from None


def _json(response: SafeHttpResult) -> list[object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(payload, dict)
        or payload.get("code") != 200
        or not isinstance(payload.get("data"), list)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return payload["data"]


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


def _job(
    row: object,
    *,
    recruitment_type: str,
    plan: str,
    detail_route: str,
) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("jobAdId") or row.get("id")
    title = row.get("jobAdName") or row.get("jobTitle")
    if (
        not isinstance(job_id, str)
        or not job_id.strip()
        or not isinstance(title, str)
        or not title.strip()
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    cities = _labels(row.get("workingPlace"))
    category = row.get("jobCategroyDescription")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    return CollectedOpportunity(
        title=title.strip(),
        target_url=(
            f"https://job.dahuatech.com/#/{detail_route}?"
            f"{urlencode({'id': job_id.strip()})}"
        ),
        recruitment_type=recruitment_type,
        plan=plan,
        location_text="、".join(cities) or "未公开",
        category_labels=categories,
        city_labels=cities,
        cohort_labels=_cohorts(title, row.get("require"), row.get("requirements")),
    )


class DahuaAdapter:
    key = "dahua-v1"
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
        recruit_type, recruitment_type, plan, detail_route = _source(source_url)
        max_opportunities = config.get("_max_opportunities", 5000)
        if (
            isinstance(max_opportunities, bool)
            or not isinstance(max_opportunities, int)
            or not 1 <= max_opportunities <= 5000
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        heartbeat()
        rows = _json(
            client.post_json(
                _API,
                {
                    "companyCategory": "",
                    "positionCategory": "",
                    "workPlaceCode": "",
                    "jobTitle": "",
                    "recruitType": recruit_type,
                },
                max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
            )
        )
        truncated = len(rows) > max_opportunities
        opportunities = tuple(
            _job(
                row,
                recruitment_type=recruitment_type,
                plan=plan,
                detail_route=detail_route,
            )
            for row in rows[:max_opportunities]
        )
        return AdapterResult(
            complete=not truncated,
            opportunities=opportunities,
            category_labels=tuple(
                dict.fromkeys(
                    label for item in opportunities for label in item.category_labels
                )
            ),
            city_labels=tuple(
                dict.fromkeys(
                    label for item in opportunities for label in item.city_labels
                )
            ),
            cohort_labels=tuple(
                dict.fromkeys(
                    label for item in opportunities for label in item.cohort_labels
                )
            ),
            pages_read=1,
            truncated=truncated,
        )


DAHUA_ADAPTER = DahuaAdapter()

__all__ = ["DAHUA_ADAPTER", "DahuaAdapter"]
