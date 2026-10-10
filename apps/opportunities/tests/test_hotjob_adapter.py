import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity, parse_published_at
from apps.opportunities.checks.hotjob import HOTJOB_ADAPTER
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError


def _response(payload, *, url="https://wecruit.hotjob.cn/source"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="招聘官网",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


def _payload(rows, *, total, total_pages, current_page, page_size=None):
    page_form = {
        "totalPage": total_pages,
        "currentPage": current_page,
        "pageData": rows,
    }
    if page_size is not None:
        page_form["pageSize"] = page_size
    return {
        "state": "200",
        "data": {
            "positonNum": total,
            "pageForm": page_form,
        },
    }


class _Client:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url, **limits):
        del limits
        self.urls.append(url)
        page = int(url.split("currentPage=", 1)[1].split("&", 1)[0])
        return self.pages[page - 1]


class _PageSizeClient:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url, **limits):
        del limits
        self.urls.append(url)
        query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
        key = (int(query["pageSize"]), int(query["currentPage"]))
        return self.pages[key]


def _row(post_id, title, *, project="2027届校园招聘", recruit_type=1):
    return {
        "postId": post_id,
        "postName": title,
        "projectName": project,
        "recruitType": recruit_type,
        "postTypeName": "研发类",
        "workPlaceStr": "浙江省·杭州市、上海市-浦东新区",
        "publishDate": "2026-08-20 12:30:00",
    }


def test_hotjob_adapter_collects_pages_and_source_publication_time():
    source = "https://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/pb/school.html"
    client = _Client(
        [
            _response(
                _payload(
                    [_row("job-1", "算法工程师")],
                    total=2,
                    total_pages=2,
                    current_page=1,
                )
            ),
            _response(
                _payload(
                    [_row("job-2", "后端工程师")],
                    total=2,
                    total_pages=2,
                    current_page=2,
                )
            ),
        ]
    )

    result = HOTJOB_ADAPTER.collect(
        source_url=source,
        config={"_max_pages": 10, "_max_opportunities": 20},
        client=client,
        initial_response=SafeHttpResult(500, source, "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 2
    assert result.opportunities[0] == CollectedOpportunity(
        title="算法工程师",
        target_url=(
            "https://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/"
            "pb/posDetail.html?postId=job-1&postType=campus"
        ),
        recruitment_type="CAMPUS",
        plan="2027届校园招聘",
        location_text="浙江省·杭州市、上海市-浦东新区",
        category_labels=("研发类",),
        city_labels=("杭州市", "上海市"),
        cohort_labels=("2027届",),
        published_at=parse_published_at("2026-08-20 12:30:00"),
    )
    assert result.opportunities[0].published_at is not None
    assert len(client.urls) == 2


def test_hotjob_adapter_accepts_empty_result_with_zero_page_size_sentinel():
    source = "https://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/pb/school.html"
    client = _Client(
        [_response(_payload([], total=0, total_pages=0, current_page=0, page_size=0))]
    )

    result = HOTJOB_ADAPTER.collect(
        source_url=source,
        config={"_max_pages": 10, "_max_opportunities": 20},
        client=client,
        initial_response=SafeHttpResult(200, source, "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.opportunities == ()
    assert result.pages_read == 1
    assert len(client.urls) == 1


def test_hotjob_comprehensive_portal_deduplicates_same_post_across_types():
    source = "https://wecruit.hotjob.cn/SU64ae46c02f9d24760adac777/pb/index.html"
    row = _row("same-job", "结构管培生")
    client = _Client(
        [
            _response(_payload([row], total=1, total_pages=1, current_page=1)),
            _response(
                _payload(
                    [dict(row, recruitType=2)],
                    total=1,
                    total_pages=1,
                    current_page=1,
                )
            ),
        ]
    )
    result = HOTJOB_ADAPTER.collect(
        source_url=source,
        config={"_max_pages": 10, "_max_opportunities": 20},
        client=client,
        initial_response=SafeHttpResult(200, source, "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert len(result.opportunities) == 1
    assert len(client.urls) == 2


def test_hotjob_adapter_restarts_with_provider_page_size_to_keep_all_rows():
    source = "https://wecruit.hotjob.cn/SU6656786d1c240e071a6867a7/mc/position/campus"
    pages = {
        # The first response is cached with Hotjob's default size of 10 even
        # though the adapter requested 15.  Subsequent requests are stable at
        # the reported size and contain all three rows.
        (15, 1): _response(
            _payload(
                [_row("job-1", "岗位一")],
                total=3,
                total_pages=3,
                current_page=1,
                page_size=10,
            )
        ),
        (10, 1): _response(
            _payload(
                [_row("job-1", "岗位一")],
                total=3,
                total_pages=3,
                current_page=1,
                page_size=10,
            )
        ),
        (10, 2): _response(
            _payload(
                [_row("job-2", "岗位二")],
                total=3,
                total_pages=3,
                current_page=2,
                page_size=10,
            )
        ),
        (10, 3): _response(
            _payload(
                [_row("job-3", "岗位三")],
                total=3,
                total_pages=3,
                current_page=3,
                page_size=10,
            )
        ),
    }
    client = _PageSizeClient(pages)

    result = HOTJOB_ADAPTER.collect(
        source_url=source,
        config={"_max_pages": 10, "_max_opportunities": 20},
        client=client,
        initial_response=SafeHttpResult(200, source, "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.truncated is False
    assert result.pages_read == 3
    assert [item.title for item in result.opportunities] == [
        "岗位一",
        "岗位二",
        "岗位三",
    ]
    assert "pageSize=15" in client.urls[0]
    assert all("pageSize=10" in url for url in client.urls[1:])


@pytest.mark.parametrize(
    "source",
    (
        "http://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/pb/school.html",
        "https://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/pb/custom.html",
        "https://example.com/SU62b2ae672f9d24458d72f9cc/pb/school.html",
    ),
)
def test_hotjob_adapter_rejects_non_canonical_source(source):
    with pytest.raises(SafeRequestError) as error:
        HOTJOB_ADAPTER.source_probe_url(source)
    assert error.value.error_code == "opportunities.adapter_config_invalid.v1"


def test_hotjob_adapter_rejects_invalid_recruitment_type_override():
    source = "https://wecruit.hotjob.cn/SU62b2ae672f9d24458d72f9cc/pb/school.html"
    with pytest.raises(SafeRequestError) as error:
        HOTJOB_ADAPTER.collect(
            source_url=source,
            config={"recruit_types": [2]},
            client=_Client([]),
            initial_response=SafeHttpResult(200, source, "", b"", False),
            heartbeat=lambda: None,
        )
    assert error.value.error_code == "opportunities.adapter_config_invalid.v1"
