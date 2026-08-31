from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit, urlunsplit

from ._aes import decrypt_aes128_cbc
from .adapters import (
    AdapterResult,
    CollectedOpportunity,
    FetchClient,
    published_at_from_mapping,
)
from .http import (
    MAX_ADAPTER_RESPONSE_BYTES,
    MAX_RESPONSE_BYTES,
    SafeHttpResult,
    SafeRequestError,
)

_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_MODES = {
    "campus-recruitment": ("campus", "CAMPUS", "校园招聘"),
    "social-recruitment": ("social", "SOCIAL", "社会招聘"),
}
_DEFAULT_AES_IV = "de7c21ed8d6f50fe"


def _json_object(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not isinstance(value, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return value


def _plain_payload(response: SafeHttpResult) -> Mapping[str, object]:
    value = _json_object(response)
    if value.get("code") != 0 or value.get("success") is not True:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return value


def _encrypted_payload(response: SafeHttpResult, *, iv: str) -> Mapping[str, object]:
    envelope = _json_object(response)
    encoded = envelope.get("data")
    key = envelope.get("necromancer")
    if not isinstance(encoded, str) or not isinstance(key, str):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        ciphertext = base64.b64decode(encoded, validate=True)
        decoded = decrypt_aes128_cbc(
            ciphertext,
            key=key.encode("ascii"),
            iv=iv.encode("ascii"),
        )
        value = json.loads(decoded.decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if (
        not isinstance(value, dict)
        or value.get("code") != 0
        or value.get("success") is not True
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return value


def _source_config(source_url: str):
    parsed = urlsplit(source_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3 or parts[0] not in _MODES or not parts[2].isdigit():
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    fragment = parsed.fragment.removeprefix("/")
    fragment_path, _, fragment_query = fragment.partition("?")
    if fragment_path and fragment_path != "jobs":
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    filters = parse_qs(fragment_query, keep_blank_values=False)

    def indexed_values(name: str) -> tuple[str, ...]:
        values = []
        for key, items in filters.items():
            suffix = key.removeprefix(f"{name}[").removesuffix("]")
            if key == f"{name}[]" or (key.startswith(f"{name}[") and suffix.isdigit()):
                values.extend(items)
        return tuple(dict.fromkeys(values))

    zhineng = indexed_values("zhineng")
    commitments = indexed_values("commitment")
    locale = parse_qs(parsed.query).get("locale", ["zh-CN"])[0]
    if locale not in ("zh-CN", "en-US"):
        locale = "zh-CN"
    site, recruitment_type, plan = _MODES[parts[0]]
    return {
        "parsed": parsed,
        "org_id": parts[1],
        "site_id": int(parts[2]),
        "site": site,
        "recruitment_type": recruitment_type,
        "plan": plan,
        "locale": locale,
        "zhineng_ids": zhineng,
        "commitments": commitments,
    }


def _labels(items: object) -> tuple[str, ...]:
    if not isinstance(items, list):
        return ()
    labels = []
    for item in items:
        if isinstance(item, dict):
            value = item.get("label") or item.get("name") or item.get("id")
        else:
            value = item
        if isinstance(value, str) and value.strip():
            labels.append(value.strip())
    return tuple(dict.fromkeys(labels))


def _filter_options(payload: Mapping[str, object]):
    try:
        fields = payload["data"]["systemFieldsAggregations"]
    except (KeyError, TypeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not isinstance(fields, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    locations = fields.get("locationAggregation") or {}
    categories = fields.get("zhinengAggregation") or {}
    if not isinstance(locations, dict) or not isinstance(categories, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    location_items = locations.get("locationList")
    location_map = {}
    if isinstance(location_items, list):
        for item in location_items:
            if not isinstance(item, dict) or not isinstance(item.get("label"), str):
                continue
            for row in item.get("locationRows") or ():
                if isinstance(row, dict) and isinstance(row.get("id"), int | str):
                    location_map[str(row["id"])] = item["label"].strip()
    return (
        _labels(categories.get("zhinengList")),
        _labels(location_items),
        location_map,
    )


def _cohorts(*values: object) -> tuple[str, ...]:
    result = []
    for value in values:
        if not isinstance(value, str):
            continue
        for year in _COHORT.findall(value):
            result.append(f"20{year}届")
    return tuple(dict.fromkeys(result))


def _detail_url(parsed, job_id: str) -> str:
    query = parsed.query
    return urlunsplit(("https", parsed.netloc, parsed.path, query, f"/job/{job_id}"))


def _job(
    row: object,
    *,
    source,
    filtered_commitments,
    location_map: Mapping[str, str],
) -> CollectedOpportunity:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    job_id = row.get("id")
    title = row.get("title")
    if not isinstance(job_id, str) or not job_id or not isinstance(title, str):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    title = title.strip()
    if not title:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    locations = row.get("locations")
    if locations is None:
        locations = []
    if not isinstance(locations, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    location_labels = []
    city_labels = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        province = location.get("provinceName")
        city = location.get("cityName")
        parts = [
            value.strip()
            for value in (province, city)
            if isinstance(value, str) and value.strip()
        ]
        if parts:
            location_labels.append("·".join(dict.fromkeys(parts)))
        location_id = location.get("id")
        mapped_city = location_map.get(str(location_id))
        if mapped_city:
            city_labels.append(mapped_city)
        elif isinstance(city, str) and city.strip():
            city_labels.append(city.strip())
    function = row.get("zhineng") or {}
    category = function.get("name") if isinstance(function, dict) else ""
    category_labels = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    commitment = row.get("commitment")
    is_internship = commitment == "实习" or filtered_commitments == ("实习",)
    recruitment_type = "INTERNSHIP" if is_internship else source["recruitment_type"]
    plan = "实习招聘" if is_internship else source["plan"]
    cohorts = _cohorts(title, row.get("jobDescription"), row.get("projectFolder"))
    return CollectedOpportunity(
        title=title,
        target_url=_detail_url(source["parsed"], job_id),
        recruitment_type=recruitment_type,
        plan=plan,
        location_text="、".join(dict.fromkeys(location_labels)) or "未公开",
        category_labels=category_labels,
        city_labels=tuple(dict.fromkeys(city_labels)),
        cohort_labels=cohorts,
        published_at=published_at_from_mapping(row),
    )


class MokaAdapter:
    key = "moka-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        parsed = _source_config(source_url)["parsed"]
        return urlunsplit(("https", parsed.netloc, "/api/env", "", ""))

    def check_opportunity(
        self,
        *,
        source_url: str,
        target_url: str,
        config: Mapping[str, object],
        client: FetchClient,
    ) -> SafeHttpResult:
        source = _source_config(source_url)
        iv = config.get("aes_iv", _DEFAULT_AES_IV)
        target = urlsplit(target_url)
        fragment = target.fragment.removeprefix("/")
        prefix, _, job_id = fragment.partition("/")
        if (
            not isinstance(iv, str)
            or len(iv.encode("utf-8")) != 16
            or target.scheme != "https"
            or target.netloc != source["parsed"].netloc
            or target.path != source["parsed"].path
            or prefix != "job"
            or not job_id
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        response = client.post_json(
            "https://app.mokahr.com/api/outer/ats-apply/website/job",
            {
                "siteId": source["site_id"],
                "orgId": source["org_id"],
                "jobId": job_id,
                "locale": source["locale"],
            },
            max_response_bytes=MAX_RESPONSE_BYTES,
        )
        payload = _encrypted_payload(response, iv=iv)
        data = payload.get("data")
        if not isinstance(data, dict) or str(data.get("id") or "") != job_id:
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
        source = _source_config(source_url)
        iv = config.get("aes_iv", _DEFAULT_AES_IV)
        page_size = config.get("page_size", 30)
        max_pages = config.get("_max_pages", 50)
        max_opportunities = config.get("_max_opportunities", 5000)
        if (
            not isinstance(iv, str)
            or len(iv.encode("utf-8")) != 16
            or isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 30
            or isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or not 1 <= max_pages <= 100
            or isinstance(max_opportunities, bool)
            or not isinstance(max_opportunities, int)
            or not 1 <= max_opportunities <= 5000
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        base = "https://app.mokahr.com/api/outer/ats-apply/website/jobs/v2"
        filter_request = {
            "zhinengIds": list(source["zhineng_ids"]),
            "orgId": source["org_id"],
            "siteId": source["site_id"],
            "locale": source["locale"],
        }
        heartbeat()
        filters = _plain_payload(
            client.post_json(f"{base}/filterFieldsAggregations", filter_request)
        )
        category_labels, city_labels, location_map = _filter_options(filters)

        opportunities = []
        page_index = 0
        truncated = False
        while True:
            heartbeat()
            request = {
                "orgId": source["org_id"],
                "siteId": str(source["site_id"]),
                "limit": page_size,
                "offset": page_index * page_size,
                "needStat": True,
                "jobIdTopList": [],
                "zhinengIds": list(source["zhineng_ids"]),
                "commitments": list(source["commitments"]),
                "customFields": {},
                "site": source["site"],
                "locale": source["locale"],
            }
            payload = _encrypted_payload(
                client.post_json(
                    base,
                    request,
                    max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
                ),
                iv=iv,
            )
            data = payload.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            rows = data["jobs"]
            opportunities.extend(
                _job(
                    row,
                    source=source,
                    filtered_commitments=source["commitments"],
                    location_map=location_map,
                )
                for row in rows
            )
            stats = data.get("jobStats") or {}
            total = stats.get("total") if isinstance(stats, dict) else None
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


MOKA_ADAPTER = MokaAdapter()

__all__ = ["MOKA_ADAPTER", "MokaAdapter"]
