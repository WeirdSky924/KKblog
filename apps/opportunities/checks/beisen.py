from __future__ import annotations

import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .adapters import (
    AdapterResult,
    CollectedOpportunity,
    FetchClient,
    published_at_from_mapping,
)
from .http import (
    MAX_ADAPTER_RESPONSE_BYTES,
    MAX_LARGE_ADAPTER_RESPONSE_BYTES,
    SafeHttpResult,
    SafeRequestError,
)

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
_TRUNCATED_PAGE_RETRY_SIZE = 20
_LEGACY_COUNT = re.compile(r"共\s*([0-9][0-9,]*)\s*条(?:记录|职位)")
_LEGACY_PAGE = re.compile(r"当前第\s*(\d+)\s*/\s*(\d+)\s*页")
_LEGACY_JOB_HREF = re.compile(
    r"/(?:zpdetail|(?:campus|intern|social)/detail)(?:/|\?|$)",
    re.IGNORECASE,
)
_LEGACY_TABLE_MARKER = re.compile(
    rb"<table\b[^>]*\bclass\s*=\s*['\"][^'\"]*\b(?:jobsTable|listtable)\b",
    re.IGNORECASE,
)
_LEGACY_ZWM_MARKER = re.compile(
    rb"<div\b[^>]*\bclass\s*=\s*['\"][^'\"]*\bzwm\b",
    re.IGNORECASE,
)
_LEGACY_ZWM_JOB_HREF = re.compile(
    r"/(?:campus|intern|social)xq(?:/|\?|$)", re.IGNORECASE
)
_PAGE_INDEX = re.compile(r"(?:^|[?&])PageIndex=(\d+)(?:&|$)", re.IGNORECASE)


class _LegacyTableParser(HTMLParser):
    """Parse the bounded table/pager shape emitted by old Zhiye portals."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, object]]] = []
        self.anchors: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self._table_depth = 0
        self._target_table = False
        self._row: list[dict[str, object]] | None = None
        self._cell: dict[str, object] | None = None
        self._anchor: dict[str, str] | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if tag == "table":
            classes = set((attributes.get("class") or "").split())
            if self._table_depth == 0 and classes.intersection(
                {"jobsTable", "listtable"}
            ):
                self._target_table = True
                self._table_depth = 1
            elif self._table_depth:
                self._table_depth += 1
            return
        if self._table_depth and tag == "tr" and self._row is None:
            self._row = []
            return
        if self._row is not None and tag == "td" and self._cell is None:
            self._cell = {
                "parts": [],
                "title": str(attributes.get("title") or ""),
                "href": "",
                "anchor_title": "",
            }
            return
        if tag == "a":
            self._anchor = {
                "href": str(attributes.get("href") or ""),
                "title": str(attributes.get("title") or ""),
            }
            self._anchor_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            self._anchor["text"] = " ".join(self._anchor_parts)
            self.anchors.append(self._anchor)
            if self._cell is not None and self._anchor.get("href"):
                self._cell["href"] = self._anchor["href"]
                self._cell["anchor_title"] = self._anchor.get("title", "")
            self._anchor = None
            self._anchor_parts = []
            return
        if tag == "td" and self._cell is not None and self._row is not None:
            self._cell["text"] = " ".join(
                str(value) for value in self._cell.pop("parts", [])
            )
            self._row.append(self._cell)
            self._cell = None
            return
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            return
        if tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                self._target_table = False

    def handle_data(self, data: str) -> None:
        if data:
            self.text_parts.append(data)
        if self._anchor is not None:
            self._anchor_parts.append(data)
        if self._cell is not None:
            self._cell.setdefault("parts", []).append(data)


class _LegacyZwmParser(HTMLParser):
    """Parse the list-and-pagination markup used by legacy Zhiye sites."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, object]] = []
        self.anchors: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self._zwm_depth = 0
        self._list_depth = 0
        self._li_depth = 0
        self._row: dict[str, object] | None = None
        self._span_depth = 0
        self._span_parts: list[str] = []
        self._anchor: dict[str, str] | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "div" and "zwm" in classes and self._zwm_depth == 0:
            self._zwm_depth = 1
            return
        if self._zwm_depth and tag == "div":
            self._zwm_depth += 1
        if self._zwm_depth and tag == "ul" and self._list_depth == 0:
            self._list_depth = 1
            return
        if self._list_depth and tag == "ul":
            self._list_depth += 1
            return
        if self._list_depth and tag == "li" and self._li_depth == 0:
            self._li_depth = 1
            self._row = {"href": "", "title": "", "spans": [], "text": []}
            return
        if self._li_depth and tag == "li":
            self._li_depth += 1
            return
        if tag == "a" and self._anchor is None:
            self._anchor = {
                "href": str(attributes.get("href") or ""),
                "title": str(attributes.get("title") or ""),
                "class": str(attributes.get("class") or ""),
            }
            self._anchor_parts = []
            return
        if self._row is not None and tag == "span":
            self._span_depth += 1
            if self._span_depth == 1:
                self._span_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._span_depth:
            self._span_depth -= 1
            if self._span_depth == 0 and self._row is not None:
                spans = self._row.setdefault("spans", [])
                if isinstance(spans, list):
                    spans.append(" ".join(self._span_parts))
                self._span_parts = []
            return
        if tag == "a" and self._anchor is not None:
            self._anchor["text"] = " ".join(self._anchor_parts)
            self.anchors.append(self._anchor)
            if self._row is not None:
                self._row["href"] = self._anchor.get("href", "")
                self._row["title"] = self._anchor.get("title", "")
                self._row["text"] = list(self._anchor_parts)
            self._anchor = None
            self._anchor_parts = []
            return
        if self._li_depth and tag == "li":
            self._li_depth -= 1
            if self._li_depth == 0 and self._row is not None:
                self.rows.append(self._row)
                self._row = None
            return
        if self._list_depth and tag == "ul":
            self._list_depth -= 1
            return
        if self._zwm_depth and tag == "div":
            self._zwm_depth -= 1

    def handle_data(self, data: str) -> None:
        if data:
            self.text_parts.append(data)
        if self._anchor is not None:
            self._anchor_parts.append(data)
        if self._span_depth:
            self._span_parts.append(data)


def _legacy_text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    return normalized[:maximum]


def _legacy_zwm_page_data(
    response: SafeHttpResult, *, source_url: str
) -> dict[str, object]:
    """Read the bounded ``zwm`` list used by legacy Zhiye portals."""
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        body = response.body.decode("utf-8")
    except UnicodeDecodeError:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    parser = _LegacyZwmParser()
    try:
        parser.feed(body)
    except Exception:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not parser.rows:
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
    source = urlsplit(source_url)
    rows: list[dict[str, object]] = []
    for raw in parser.rows:
        href = _legacy_text(raw.get("href"), maximum=2048)
        if not href or not _LEGACY_ZWM_JOB_HREF.search(urlsplit(href).path):
            continue
        target_url = urljoin(source_url, href)
        target = urlsplit(target_url)
        if target.scheme != "https" or target.hostname != source.hostname:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        spans = raw.get("spans")
        if not isinstance(spans, list):
            spans = []
        values = [_legacy_text(value, maximum=300) for value in spans]
        title = (
            values[1]
            if len(values) > 1
            else _legacy_text(raw.get("title"), maximum=200)
        )
        if not title:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        location = values[3] if len(values) > 3 else ""
        category = values[0] if values else ""
        row_text = _legacy_text(" ".join(values), maximum=500)
        rows.append(
            {
                "title": title,
                "target_url": target_url,
                "location": location,
                "category": category,
                "published": "",
                "row_text": row_text,
            }
        )
    if not rows:
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")

    query = dict(parse_qsl(source.query, keep_blank_values=True))
    current_page = 1
    for key, value in query.items():
        if key.casefold() == "pageindex" and value.isdigit():
            current_page = int(value)
            break
    page_numbers = [current_page]
    next_url = ""
    for anchor in parser.anchors:
        href = _legacy_text(anchor.get("href"), maximum=2048)
        label = _legacy_text(anchor.get("text"), maximum=40)
        if href:
            linked = urlsplit(urljoin(source_url, href))
            match = _PAGE_INDEX.search(linked.query)
            if match:
                page_numbers.append(int(match.group(1)))
        classes = set((anchor.get("class") or "").split())
        if href and (
            "下一页" in label or ("next" in classes and "上一页" not in label)
        ):
            next_url = urljoin(source_url, href)
    return {
        "rows": rows,
        "total": None,
        "current_page": current_page,
        "total_pages": max(page_numbers),
        "next_url": next_url,
    }


def _legacy_page_data(
    response: SafeHttpResult, *, source_url: str
) -> dict[str, object]:
    if _LEGACY_ZWM_MARKER.search(response.body):
        return _legacy_zwm_page_data(response, source_url=source_url)
    if response.truncated or not 200 <= response.status < 300:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    try:
        body = response.body.decode("utf-8")
    except UnicodeDecodeError:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    parser = _LegacyTableParser()
    try:
        parser.feed(body)
    except Exception:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1") from None
    if not parser.rows:
        raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
    headers = [_legacy_text(cell.get("text"), maximum=100) for cell in parser.rows[0]]
    title_index = next(
        (
            index
            for index, value in enumerate(headers)
            if "职位" in value or "岗位" in value
        ),
        0,
    )
    location_index = next(
        (
            index
            for index, value in enumerate(headers)
            if "地点" in value or "城市" in value
        ),
        None,
    )
    published_index = next(
        (
            index
            for index, value in enumerate(headers)
            if "发布" in value or "日期" in value or "时间" in value
        ),
        None,
    )
    category_index = next(
        (
            index
            for index, value in enumerate(headers)
            if "类型" in value or "类别" in value or "方向" in value
        ),
        1 if len(headers) > 1 else None,
    )
    rows: list[dict[str, object]] = []
    for cells in parser.rows[1:]:
        if title_index >= len(cells):
            continue
        title_cell = cells[title_index]
        href = _legacy_text(title_cell.get("href"), maximum=2048)
        if not href or not _LEGACY_JOB_HREF.search(urlsplit(href).path):
            continue
        title = _legacy_text(
            title_cell.get("anchor_title") or title_cell.get("text"),
            maximum=200,
        )
        if not title:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        target_url = urljoin(source_url, href)
        target = urlsplit(target_url)
        source = urlsplit(source_url)
        if target.scheme != "https" or target.hostname != source.hostname:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        location = ""
        if location_index is not None and location_index < len(cells):
            location = _legacy_text(
                cells[location_index].get("title") or cells[location_index].get("text"),
                maximum=300,
            )
        category = ""
        if category_index is not None and category_index < len(cells):
            category = _legacy_text(cells[category_index].get("text"), maximum=100)
        published = ""
        if published_index is not None and published_index < len(cells):
            published = _legacy_text(cells[published_index].get("text"), maximum=80)
        row_text = " ".join(
            _legacy_text(cell.get("text"), maximum=300) for cell in cells
        )
        rows.append(
            {
                "title": title,
                "target_url": target_url,
                "location": location,
                "category": category,
                "published": published,
                "row_text": row_text,
            }
        )
    if not rows:
        count_match = _LEGACY_COUNT.search(" ".join(parser.text_parts))
        if count_match is None or int(count_match.group(1).replace(",", "")) != 0:
            raise SafeRequestError("opportunities.adapter_page_config_invalid.v1")
    count_match = _LEGACY_COUNT.search(" ".join(parser.text_parts))
    total = (
        int(count_match.group(1).replace(",", "")) if count_match is not None else None
    )
    page_match = _LEGACY_PAGE.search(" ".join(parser.text_parts))
    current_page = int(page_match.group(1)) if page_match else 1
    total_pages = int(page_match.group(2)) if page_match else 1
    next_url = ""
    for anchor in parser.anchors:
        label = _legacy_text(anchor.get("text"), maximum=40)
        href = _legacy_text(anchor.get("href"), maximum=2048)
        if href and ("下一页" in label or label.casefold() == "next"):
            next_url = urljoin(source_url, href)
            break
    return {
        "rows": rows,
        "total": total,
        "current_page": current_page,
        "total_pages": total_pages,
        "next_url": next_url,
    }


def _legacy_city_labels(value: str) -> tuple[str, ...]:
    labels = []
    for item in re.split(r"[,，、/;；|]", value):
        item = item.strip()
        if not item:
            continue
        city = item.rsplit("-", 1)[-1].strip()
        if city and city not in labels:
            labels.append(city)
    return tuple(labels)


def _legacy_opportunity(
    row: Mapping[str, object], *, source_kind: str
) -> CollectedOpportunity:
    title = row.get("title")
    target_url = row.get("target_url")
    if not isinstance(title, str) or not title or not isinstance(target_url, str):
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    kind = source_kind if source_kind in _RECRUITMENT_TYPE else "jobs"
    recruitment_type = _RECRUITMENT_TYPE.get(kind, "OTHER")
    plan = _PLAN.get(kind, "官方招聘")
    location = _legacy_text(row.get("location"), maximum=300) or "未公开"
    category = _legacy_text(row.get("category"), maximum=100)
    row_text = _legacy_text(row.get("row_text"), maximum=500)
    return CollectedOpportunity(
        title=title,
        target_url=target_url,
        recruitment_type=recruitment_type,
        plan=plan,
        location_text=location,
        category_labels=(category,) if category else (),
        city_labels=_legacy_city_labels(location),
        cohort_labels=_cohorts(title, row_text),
        published_at=published_at_from_mapping({"publishDate": row.get("published")}),
    )


def _collect_legacy(
    *,
    source_url: str,
    config: Mapping[str, object],
    client: FetchClient,
    initial_response: SafeHttpResult,
    heartbeat,
) -> AdapterResult:
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
    response = initial_response
    current_url = source_url
    opportunities: list[CollectedOpportunity] = []
    identities: set[tuple[str, str]] = set()
    total: int | None = None
    total_pages: int | None = None
    pages_read = 0
    truncated = False
    while True:
        heartbeat()
        page = _legacy_page_data(response, source_url=current_url)
        pages_read += 1
        page_total = page["total"]
        page_count = page["total_pages"]
        if page_total is not None:
            if total is not None and page_total != total:
                raise SafeRequestError("opportunities.adapter_response_invalid.v1")
            total = page_total
        if total_pages is not None and page_count != total_pages:
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        total_pages = page_count
        for raw in page["rows"]:
            item = _legacy_opportunity(raw, source_kind=source_kind)
            identity = (item.target_url, item.title.casefold())
            if identity in identities:
                raise SafeRequestError("opportunities.adapter_duplicate_identity.v1")
            identities.add(identity)
            opportunities.append(item)
            if len(opportunities) >= max_opportunities:
                truncated = total is None or len(opportunities) < total
                opportunities = opportunities[:max_opportunities]
                break
        if truncated:
            break
        current_page = int(page["current_page"])
        next_url = str(page["next_url"] or "")
        if total is not None and len(opportunities) >= total:
            break
        if current_page >= int(total_pages or 1) and not next_url:
            if total in (None, len(opportunities)):
                break
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        if pages_read >= max_pages:
            truncated = True
            break
        if not next_url:
            parsed = urlsplit(current_url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            key = next(
                (key for key in query if key.casefold() == "pageindex"), "PageIndex"
            )
            query[key] = str(current_page + 1)
            next_url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urlencode(query),
                    parsed.fragment,
                )
            )
        next_parsed = urlsplit(next_url)
        source_parsed = urlsplit(source_url)
        if (
            next_parsed.scheme != "https"
            or next_parsed.hostname != source_parsed.hostname
        ):
            raise SafeRequestError("opportunities.adapter_response_invalid.v1")
        current_url = next_url
        # Legacy list pages include the full table and need the bounded adapter
        # response limit rather than the generic probe limit.
        response = client.get(
            current_url, max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES
        )
    if not truncated and total is not None and len(opportunities) != total:
        raise SafeRequestError("opportunities.adapter_response_invalid.v1")
    categories = tuple(
        dict.fromkeys(label for item in opportunities for label in item.category_labels)
    )
    cities = tuple(
        dict.fromkeys(label for item in opportunities for label in item.city_labels)
    )
    cohorts = tuple(
        dict.fromkeys(label for item in opportunities for label in item.cohort_labels)
    )
    return AdapterResult(
        complete=not truncated,
        opportunities=tuple(opportunities),
        category_labels=categories,
        city_labels=cities,
        cohort_labels=cohorts,
        pages_read=max(1, pages_read),
        truncated=truncated,
    )


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
    locations = row.get("LocNames")
    if locations is None:
        locations = []
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
        published_at=published_at_from_mapping(row),
    )


class BeisenZhiyeAdapter:
    key = "beisen-zhiye-v1"
    browser_required = False
    authoritative_listing = True
    source_probe_max_response_bytes = MAX_LARGE_ADAPTER_RESPONSE_BYTES

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
        if _LEGACY_TABLE_MARKER.search(
            initial_response.body
        ) or _LEGACY_ZWM_MARKER.search(initial_response.body):
            return _collect_legacy(
                source_url=source_url,
                config=config,
                client=client,
                initial_response=initial_response,
                heartbeat=heartbeat,
            )
        max_pages = config.get("_max_pages", 50)
        max_opportunities = config.get("_max_opportunities", 5000)
        page_size = config.get("page_size", 100)
        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or not 1 <= max_pages <= 100
            or isinstance(max_opportunities, bool)
            or not isinstance(max_opportunities, int)
            or not 1 <= max_opportunities <= 5000
            or isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 100
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
        truncated = False
        page_size_retries = 0
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
            response = client.post_json(
                f"{base}/api/Jobad/GetJobAdPageList",
                jobs_request,
                max_response_bytes=MAX_LARGE_ADAPTER_RESPONSE_BYTES,
            )
            if response.truncated and page_size > 1 and page_size_retries < 3:
                retry_page_size = min(page_size, _TRUNCATED_PAGE_RETRY_SIZE)
                page_size = (
                    retry_page_size
                    if retry_page_size < page_size
                    else max(1, page_size // 2)
                )
                page_size_retries += 1
                page_index = 0
                opportunities.clear()
                continue
            payload = _json_object(response)
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
