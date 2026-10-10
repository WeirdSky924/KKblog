"""安全读取大易/Hotjob 公开职位列表。

Hotjob 的公开页面是前端壳，职位列表由同一官方租户的只读分页接口提供。
适配器只接受带有明确租户编号和列表页面形状的 canonical ``wecruit`` URL，
不跟随企业别名页自行扩大信任边界。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from urllib.parse import urlencode, urlsplit

from .adapters import (
    AdapterResult,
    CollectedOpportunity,
    FetchClient,
    published_at_from_mapping,
)
from .http import MAX_RESPONSE_BYTES, SafeHttpResult, SafeRequestError

_TENANT_PATH = re.compile(r"^/(SU[A-Za-z0-9]{20,64})(/.+)$")
_POST_ID = re.compile(r"^[A-Za-z0-9_-]{4,160}$")
_COHORT = re.compile(r"(?<!\d)(?:20)?(\d{2})\s*届")
_LOCATION_SPLIT = re.compile(r"[,，、/;；|]")
_API_PREFIX = "/wecruit/positionInfo/listPosition/"

# Hotjob aliases expose the same tenant API on their own host.  Keep this
# finite allowlist in the adapter so a source URL cannot expand the network
# trust boundary at runtime.
HOTJOB_SOURCE_HOSTS = frozenset(
    {
        "wecruit.hotjob.cn",
        "cgwx.hotjob.cn",
        "essence.hotjob.cn",
        "faw-vw.hotjob.cn",
        "gcoreinc.hotjob.cn",
        "positec.hotjob.cn",
        "seazen.hotjob.cn",
        "skyworth.hotjob.cn",
        "travelsky.hotjob.cn",
    }
)

# The path determines the public recruitment context.  ``mc/index`` and
# ``pb/index.html`` are combined portals, so both public API recruitment types
# are collected and deduplicated by the provider's stable post id.
_MODES: dict[str, tuple[tuple[int, ...], str, str]] = {
    "/pb/school.html": ((1,), "CAMPUS", "校园招聘"),
    "/pb/social.html": ((2,), "SOCIAL", "社会招聘"),
    "/pb/interns.html": ((2,), "INTERNSHIP", "实习招聘"),
    "/mc/position/campus": ((1,), "CAMPUS", "校园招聘"),
    "/mc/position/social": ((2,), "SOCIAL", "社会招聘"),
    "/mc/position/intern": ((2,), "INTERNSHIP", "实习招聘"),
    "/pb/index.html": ((1, 2), "COMPREHENSIVE", "官方招聘"),
    "/mc/index": ((1, 2), "COMPREHENSIVE", "官方招聘"),
}


def _source_config(source_url: str) -> dict[str, object]:
    parsed = urlsplit(source_url)
    match = _TENANT_PATH.fullmatch(parsed.path.rstrip("/") or "/")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOTJOB_SOURCE_HOSTS
        or match is None
        or match.group(2).rstrip("/") not in _MODES
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    path = match.group(2).rstrip("/")
    recruitment_types, fixed_type, plan = _MODES[path]
    return {
        "parsed": parsed,
        "host": parsed.hostname,
        "tenant": match.group(1),
        "path": path,
        "recruitment_types": recruitment_types,
        "fixed_type": fixed_type,
        "plan": plan,
    }


def _configured_recruitment_types(
    config: Mapping[str, object], defaults: tuple[int, ...]
) -> tuple[int, ...]:
    raw = config.get("recruit_types")
    if raw is None:
        return defaults
    if not isinstance(raw, list) or not raw or len(raw) > 2:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    values: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        if value not in values:
            values.append(value)
    selected = tuple(values)
    if any(value not in defaults for value in selected):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    return selected


def _json(response: SafeHttpResult) -> Mapping[str, object]:
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not isinstance(payload, dict) or payload.get("state") != "200":
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    return data


def _page(
    response: SafeHttpResult,
) -> tuple[list[object], int, int, int, int | None]:
    data = _json(response)
    form = data.get("pageForm")
    if not isinstance(form, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    rows = form.get("pageData")
    total_pages = form.get("totalPage")
    current_page = form.get("currentPage")
    page_size = form.get("pageSize")
    total = data.get("positonNum")
    if not isinstance(rows, list):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    if (
        isinstance(total_pages, bool)
        or not isinstance(total_pages, int)
        or total_pages < 0
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    if current_page is None:
        current_page = 1
    if isinstance(current_page, bool) or not isinstance(current_page, int):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    empty_result = not rows and total_pages == 0 and total == 0
    if page_size is not None and (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or (page_size == 0 and not empty_result)
        or (page_size != 0 and not 1 <= page_size <= 100)
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    if empty_result and page_size == 0:
        page_size = None
    return rows, total_pages, total, current_page, page_size


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        dict.fromkeys(
            item.strip() for item in _LOCATION_SPLIT.split(value) if item.strip()
        )
    )


def _city_labels(value: object) -> tuple[str, ...]:
    """Derive conservative city labels without merging unrelated locations."""
    cities: list[str] = []
    for location in _labels(value):
        city = location.rsplit("·", 1)[-1].split("-", 1)[0].strip()
        if city and city not in cities:
            cities.append(city)
    return tuple(cities)


def _cohorts(*values: object) -> tuple[str, ...]:
    labels: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        for year in _COHORT.findall(value):
            label = f"20{year}届"
            if label not in labels:
                labels.append(label)
    return tuple(labels)


def _recruitment_type(row: Mapping[str, object], *, requested: int, fixed: str) -> str:
    if fixed != "COMPREHENSIVE":
        return fixed
    text = " ".join(
        value.strip()
        for value in (
            row.get("projectName"),
            row.get("postName"),
            row.get("postTypeName"),
        )
        if isinstance(value, str)
    )
    if "实习" in text or "intern" in text.casefold():
        return "INTERNSHIP"
    if any(token in text for token in ("校招", "校园", "应届", "届")) or requested == 1:
        return "CAMPUS"
    return "SOCIAL"


def _detail_url(source: Mapping[str, object], *, post_id: str, requested: int) -> str:
    tenant = str(source["tenant"])
    path = str(source["path"])
    if path.startswith("/pb/"):
        if path == "/pb/interns.html":
            post_type = "intern"
        elif path == "/pb/social.html":
            post_type = "social"
        else:
            post_type = "campus" if requested == 1 else "social"
        return (
            f"https://{source['host']}/{tenant}/pb/posDetail.html?"
            f"{urlencode({'postId': post_id, 'postType': post_type})}"
        )
    return (
        f"https://{source['host']}/{tenant}/mc/detail?"
        f"{urlencode({'postId': post_id, 'recruitType': requested})}"
    )


def _job(
    row: object,
    *,
    source: Mapping[str, object],
    requested: int,
) -> tuple[str, CollectedOpportunity]:
    if not isinstance(row, dict):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    raw_post_id = row.get("postId")
    title = row.get("postName")
    if (
        isinstance(raw_post_id, bool)
        or not isinstance(raw_post_id, int | str)
        or not _POST_ID.fullmatch(str(raw_post_id).strip())
    ):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    if not isinstance(title, str) or not title.strip():
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    post_id = str(raw_post_id).strip()
    title = title.strip()
    category = row.get("postTypeName")
    categories = (
        (category.strip(),) if isinstance(category, str) and category.strip() else ()
    )
    recruitment_type = _recruitment_type(
        row,
        requested=requested,
        fixed=str(source["fixed_type"]),
    )
    plan_value = row.get("projectName")
    plan = (
        plan_value.strip()
        if isinstance(plan_value, str) and plan_value.strip()
        else str(source["plan"])
    )
    item = CollectedOpportunity(
        title=title,
        target_url=_detail_url(source, post_id=post_id, requested=requested),
        recruitment_type=recruitment_type,
        plan=plan,
        location_text=str(row.get("workPlaceStr") or "").strip() or "未公开",
        category_labels=categories,
        city_labels=_city_labels(row.get("workPlaceStr")),
        cohort_labels=_cohorts(
            title,
            row.get("projectName"),
            row.get("educationStr"),
        ),
        published_at=published_at_from_mapping(row),
    )
    return post_id, item


def _api_url(
    host: str,
    tenant: str,
    *,
    recruitment_type: int,
    page: int,
    page_size: int,
) -> str:
    return (
        "https://"
        + host
        + _API_PREFIX
        + tenant
        + "?"
        + urlencode(
            {
                "recruitType": recruitment_type,
                "pageSize": page_size,
                "currentPage": page,
                "isFrompb": "true",
            }
        )
    )


class HotjobAdapter:
    key = "hotjob-v1"
    browser_required = False
    authoritative_listing = True

    def source_probe_url(self, source_url: str) -> str:
        _source_config(source_url)
        # The runner performs a lightweight GET probe first.  The API itself
        # is fetched in ``collect`` with the same safe client and limits.
        return source_url

    def check_opportunity(
        self,
        *,
        source_url: str,
        target_url: str,
        config: Mapping[str, object],
        client: FetchClient,
    ) -> SafeHttpResult:
        del config
        source = _source_config(source_url)
        target = urlsplit(target_url)
        if target.scheme != "https" or target.hostname != source["host"]:
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        tenant = str(source["tenant"])
        if not target.path.startswith(f"/{tenant}/"):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        return client.get(target_url, max_response_bytes=MAX_RESPONSE_BYTES)

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
        defaults = source["recruitment_types"]
        assert isinstance(defaults, tuple)
        recruitment_types = _configured_recruitment_types(config, defaults)
        configured_page_size = config.get("page_size", 15)
        if (
            isinstance(configured_page_size, bool)
            or not isinstance(configured_page_size, int)
            or not 1 <= configured_page_size <= 100
        ):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        opportunities: list[CollectedOpportunity] = []
        seen: dict[str, CollectedOpportunity] = {}
        pages_read = 0
        requests_read = 0
        truncated = False

        for recruitment_type in recruitment_types:
            page = 1
            request_page_size = configured_page_size
            page_size_restarted = False
            total_pages: int | None = None
            total_items: int | None = None
            raw_items = 0
            while True:
                if requests_read >= max_pages:
                    truncated = True
                    break
                heartbeat()
                response = client.get(
                    _api_url(
                        str(source["host"]),
                        str(source["tenant"]),
                        recruitment_type=recruitment_type,
                        page=page,
                        page_size=request_page_size,
                    ),
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
                requests_read += 1
                (
                    rows,
                    current_pages,
                    current_total,
                    current_page,
                    reported_page_size,
                ) = _page(response)
                # A few Hotjob tenants cache the first response with their
                # default page size, then honor the requested size on later
                # pages.  Re-start once with the provider-reported size so
                # pagination remains complete instead of silently skipping
                # rows or treating a harmless metadata drift as a failure.
                if (
                    page == 1
                    and reported_page_size is not None
                    and reported_page_size != request_page_size
                    and not page_size_restarted
                ):
                    request_page_size = reported_page_size
                    page_size_restarted = True
                    total_pages = None
                    total_items = None
                    raw_items = 0
                    continue
                pages_read += 1
                if current_page not in (0, page):
                    raise SafeRequestError("opportunities.adapter_response_invalid.v1")
                if (
                    reported_page_size is not None
                    and reported_page_size != request_page_size
                ):
                    raise SafeRequestError("opportunities.adapter_response_invalid.v1")
                if total_pages is None:
                    total_pages = current_pages
                    total_items = current_total
                elif current_pages != total_pages or current_total != total_items:
                    raise SafeRequestError("opportunities.adapter_response_invalid.v1")
                raw_items += len(rows)
                for row in rows:
                    post_id, item = _job(
                        row,
                        source=source,
                        requested=recruitment_type,
                    )
                    previous = seen.get(post_id)
                    if previous is not None:
                        if (
                            previous.title != item.title
                            or previous.location_text != item.location_text
                            or previous.category_labels != item.category_labels
                            or previous.city_labels != item.city_labels
                            or previous.cohort_labels != item.cohort_labels
                            or previous.published_at != item.published_at
                        ):
                            raise SafeRequestError(
                                "opportunities.adapter_response_invalid.v1"
                            )
                        continue
                    seen[post_id] = item
                    opportunities.append(item)
                    if len(opportunities) > max_opportunities:
                        opportunities = opportunities[:max_opportunities]
                        truncated = True
                        break
                if truncated:
                    break
                if current_pages == 0 or page >= current_pages or not rows:
                    break
                page += 1
            if truncated:
                break
            if total_items is None or raw_items != total_items:
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
            opportunities=tuple(opportunities[:max_opportunities]),
            category_labels=categories,
            city_labels=cities,
            cohort_labels=cohorts,
            pages_read=max(1, pages_read),
            truncated=truncated,
        )


HOTJOB_ADAPTER = HotjobAdapter()

__all__ = ["HOTJOB_ADAPTER", "HOTJOB_SOURCE_HOSTS", "HotjobAdapter"]
