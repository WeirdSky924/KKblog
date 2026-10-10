import gzip
import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.beisen import BEISEN_ZHIYE_ADAPTER
from apps.opportunities.checks.http import (
    MAX_ADAPTER_RESPONSE_BYTES,
    MAX_LARGE_ADAPTER_RESPONSE_BYTES,
    MAX_RESPONSE_BYTES,
    SafeHttpClient,
    SafeHttpResult,
    TransportResponse,
)


def _result(payload, *, url="https://jobs.example.com/api"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


def test_safe_http_client_posts_bounded_json_through_the_pinned_transport():
    requests = []

    def transport(request):
        requests.append(request)
        return TransportResponse(
            200,
            {"content-type": "application/json"},
            b'{"Code":200}',
        )

    client = SafeHttpClient(
        allowed_hosts=("jobs.example.com",),
        resolver=lambda hostname: ("8.8.8.8",),
        transport=transport,
        monotonic=lambda: 1,
        sleeper=lambda seconds: None,
    )

    result = client.post_json(
        "https://jobs.example.com/api/jobs",
        {"PageIndex": 0, "Category": ["2"]},
    )

    assert result.status == 200
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].headers["Content-Type"] == "application/json"
    assert json.loads(requests[0].body) == {"PageIndex": 0, "Category": ["2"]}


def test_safe_http_client_allows_only_bounded_adapter_request_headers():
    requests = []

    def transport(request):
        requests.append(request)
        return TransportResponse(200, {}, b"{}")

    client = SafeHttpClient(
        allowed_hosts=("jobs.example.com",),
        resolver=lambda hostname: ("8.8.8.8",),
        transport=transport,
        monotonic=lambda: 1,
        sleeper=lambda seconds: None,
    )

    client.post_json(
        "https://jobs.example.com/api/jobs",
        {"page": 1},
        headers={
            "Origin": "https://jobs.example.com",
            "Referer": "https://jobs.example.com/campus",
            "X-Jalor-TenantAlias": "hcm",
            "X-HW-ID": "public-app",
        },
    )

    assert requests[0].headers["Origin"] == "https://jobs.example.com"
    assert requests[0].headers["X-Jalor-TenantAlias"] == "hcm"
    with pytest.raises(ValueError, match="Invalid adapter request headers"):
        client.post_json(
            "https://jobs.example.com/api/jobs",
            {"page": 1},
            headers={"Host": "internal.example.com"},
        )


def test_safe_http_client_decodes_gzip_with_the_response_size_limit():
    payload = json.dumps({"Code": 200, "Data": ["杭州"]}).encode()

    def transport(request):
        return TransportResponse(
            200,
            {"content-encoding": "gzip"},
            gzip.compress(payload),
        )

    client = SafeHttpClient(
        allowed_hosts=("jobs.example.com",),
        resolver=lambda hostname: ("8.8.8.8",),
        transport=transport,
        monotonic=lambda: 1,
        sleeper=lambda seconds: None,
    )

    decoded = client.get(
        "https://jobs.example.com/api/conditions",
        max_response_bytes=len(payload),
    )
    truncated = client.get(
        "https://jobs.example.com/api/conditions",
        max_response_bytes=len(payload) - 1,
    )

    assert decoded.body == payload
    assert decoded.truncated is False
    assert truncated.body == payload[:-1]
    assert truncated.truncated is True


def test_safe_http_client_keeps_default_and_adapter_response_limits_bounded():
    requests = []

    def transport(request):
        requests.append(request)
        return TransportResponse(200, {}, b"{}")

    client = SafeHttpClient(
        allowed_hosts=("jobs.example.com",),
        resolver=lambda hostname: ("8.8.8.8",),
        transport=transport,
        monotonic=lambda: 1,
        sleeper=lambda seconds: None,
    )

    client.get("https://jobs.example.com/api/default")
    client.get(
        "https://jobs.example.com/api/adapter",
        max_response_bytes=MAX_ADAPTER_RESPONSE_BYTES,
    )
    client.get(
        "https://jobs.example.com/api/large-adapter",
        max_response_bytes=MAX_LARGE_ADAPTER_RESPONSE_BYTES,
    )

    assert [request.max_response_bytes for request in requests] == [
        MAX_RESPONSE_BYTES,
        MAX_ADAPTER_RESPONSE_BYTES,
        MAX_LARGE_ADAPTER_RESPONSE_BYTES,
    ]
    with pytest.raises(ValueError, match="Invalid safe request limit"):
        client.get(
            "https://jobs.example.com/api/oversized",
            max_response_bytes=MAX_LARGE_ADAPTER_RESPONSE_BYTES + 1,
        )


class _BeisenClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        if url.endswith("GetJobAdSearchConditions"):
            return _result(
                {
                    "Code": 200,
                    "Data": [
                        {
                            "Value": "LocId",
                            "Data": [
                                {"Text": "杭州市"},
                                {"Text": "南昌市"},
                            ],
                        },
                        {
                            "Value": "ClassificationOne",
                            "Data": [
                                {"Text": "技术"},
                                {"Text": "职能"},
                            ],
                        },
                    ],
                }
            )
        return _result(
            {
                "Code": 200,
                "Count": 1,
                "Data": [
                    {
                        "JobAdId": 390782190,
                        "JobAdName": "前端开发工程师-26届秋招(J10377)",
                        "CategoryId": "2",
                        "LocNames": ["浙江省·杭州市"],
                        "ClassificationOne": "技术",
                        "ClassificationTwo": "杭州",
                        "Require": "2026届本科毕业生。",
                    }
                ],
            }
        )


class _BeisenAllJobsClient(_BeisenClient):
    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        if url.endswith("GetJobAdSearchConditions"):
            return _result(
                {
                    "Code": 200,
                    "Data": [
                        {"Value": "LocId", "Data": [{"Text": "杭州市"}]},
                        {
                            "Value": "Category",
                            "Data": [
                                {"Text": "社会招聘"},
                                {"Text": "校园招聘"},
                            ],
                        },
                    ],
                }
            )
        return _result(
            {
                "Code": 200,
                "Count": 1,
                "Data": [
                    {
                        "JobAdId": 190803249,
                        "JobAdName": "GEO大客户销售",
                        "CategoryId": "1",
                        "LocNames": ["浙江省·杭州市"],
                        "ClassificationOne": "销售",
                    }
                ],
            }
        )


class _BeisenLimitedClient(_BeisenClient):
    def post_json(self, url, payload, **limits):
        if url.endswith("GetJobAdSearchConditions"):
            return super().post_json(url, payload, **limits)
        self.posts.append((url, payload, limits))
        return _result(
            {
                "Code": 200,
                "Count": 4,
                "Data": [
                    {
                        "JobAdId": index,
                        "JobAdName": f"岗位 {index}",
                        "CategoryId": "2",
                        "LocNames": ["浙江省·杭州市"],
                    }
                    for index in range(1, 5)
                ],
            }
        )


def test_beisen_adapter_collects_jobs_and_source_filter_options():
    page_config = {
        "Pages": [
            {
                "Key": "campus-page-id",
                "PageType": 2,
                "BusinessType": "2",
                "Config": json.dumps(
                    {
                        "extraBusinessSetting": {
                            "JobAdListSetting": {
                                "FilterItems": [
                                    {"Key": "LocId"},
                                    {"Key": "ClassificationOne"},
                                ]
                            }
                        }
                    }
                ),
            }
        ]
    }
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/campus/jobs",
        title="校园招聘",
        body=(
            "<script>BSGlobal = "
            + json.dumps(page_config, ensure_ascii=False)
            + "; BSGlobal.staticPath='x';</script>"
        ).encode(),
        truncated=False,
    )
    client = _BeisenClient()
    heartbeats = []

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={},
        client=client,
        initial_response=initial,
        heartbeat=lambda: heartbeats.append(True),
    )

    assert result.complete is True
    assert result.pages_read == 1
    assert result.category_labels == ("技术", "职能")
    assert result.city_labels == ("杭州市", "南昌市")
    assert result.cohort_labels == ("2026届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="前端开发工程师-26届秋招(J10377)",
            target_url="https://jobs.example.com/campus/detail?jobAdId=390782190",
            recruitment_type="CAMPUS",
            plan="校园招聘",
            location_text="浙江省·杭州市",
            category_labels=("技术",),
            city_labels=("杭州市",),
            cohort_labels=("2026届",),
        ),
    )
    assert [post[0].rsplit("/", 1)[-1] for post in client.posts] == [
        "GetJobAdSearchConditions",
        "GetJobAdPageList",
    ]
    assert heartbeats


def test_beisen_all_jobs_page_maps_each_jobs_recruitment_category():
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/jobs",
        title="全部职位",
        body=(
            "<script>BSGlobal = "
            + json.dumps(
                {
                    "Pages": [
                        {
                            "Key": "all-jobs-page-id",
                            "PageType": 5,
                            "BusinessType": None,
                            "Config": "{}",
                        }
                    ]
                }
            )
            + ";</script>"
        ).encode(),
        truncated=False,
    )
    client = _BeisenAllJobsClient()

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"_max_pages": 3, "_max_opportunities": 20},
        client=client,
        initial_response=initial,
        heartbeat=lambda: None,
    )

    job = result.opportunities[0]
    assert job.recruitment_type == "SOCIAL"
    assert job.plan == "社会招聘"
    assert job.target_url == "https://jobs.example.com/social/detail?jobAdId=190803249"
    assert "Category" not in client.posts[0][1]
    assert "Category" not in client.posts[1][1]


def test_beisen_adapter_truncates_when_complete_first_page_exceeds_item_limit():
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/campus/jobs",
        title="校园招聘",
        body=(
            "<script>BSGlobal = "
            + json.dumps(
                {
                    "Pages": [
                        {
                            "Key": "campus-page-id",
                            "PageType": 2,
                            "BusinessType": "2",
                            "Config": "{}",
                        }
                    ]
                }
            )
            + ";</script>"
        ).encode(),
        truncated=False,
    )

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"_max_pages": 3, "_max_opportunities": 3},
        client=_BeisenLimitedClient(),
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is False
    assert result.truncated is True
    assert len(result.opportunities) == 3


class _LegacyBeisenClient:
    def __init__(self, page):
        self.page = page
        self.urls = []

    def get(self, url, **limits):
        del limits
        self.urls.append(url)
        return self.page


def _legacy_page(*, page: int, total_pages: int = 2) -> SafeHttpResult:
    job_id = 100 + page
    html = f"""
    <div class="joblist">
      <table class="jobsTable">
        <tr class="title"><td>职位名称</td><td>职位类型</td><td>工作地点</td><td>发布时间</td></tr>
        <tr>
          <td><a title="研发工程师-校招(J{job_id})" href="/zpdetail/{job_id}?PageIndex={page}">研发工程师-校招(J{job_id})</a></td>
          <td title="研发">研发</td>
          <td title="浙江省-杭州市">浙江省-杭州市</td>
          <td>2026-08-{15 + page:02d}</td>
        </tr>
      </table>
    </div>
    <div class="pager"><div class="counts">共2条记录</div>
      <div class="tablefooter">当前第{page}/{total_pages}页
        <a href="/campus/?PageIndex={min(page + 1, total_pages)}">下一页</a>
      </div>
    </div>
    """
    return SafeHttpResult(
        status=200,
        final_url=f"https://legacy.example.com/campus/?PageIndex={page}",
        title="校园招聘",
        body=html.encode(),
        truncated=False,
    )


def test_beisen_adapter_collects_legacy_server_rendered_pages():
    initial = _legacy_page(page=1)
    client = _LegacyBeisenClient(_legacy_page(page=2))

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"_max_pages": 10, "_max_opportunities": 20},
        client=client,
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 2
    assert len(result.opportunities) == 2
    assert result.category_labels == ("研发",)
    assert result.city_labels == ("杭州市",)
    assert result.opportunities[0].target_url == (
        "https://legacy.example.com/zpdetail/101?PageIndex=1"
    )
    assert result.opportunities[0].published_at is not None
    assert client.urls == [
        "https://legacy.example.com/campus/?PageIndex=2",
    ]


class _BeisenPageSizeClient(_BeisenClient):
    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        if url.endswith("GetJobAdSearchConditions"):
            return _result(
                {
                    "Code": 200,
                    "Data": [
                        {"Value": "LocId", "Data": []},
                        {"Value": "ClassificationOne", "Data": []},
                    ],
                }
            )
        page_size = payload["PageSize"]
        page_index = payload["PageIndex"]
        rows = [
            {
                "JobAdId": page_index * page_size + index,
                "JobAdName": f"岗位 {page_index * page_size + index}",
                "CategoryId": "2",
                "LocNames": ["浙江省·杭州市"],
            }
            for index in range(min(page_size, 21 - page_index * page_size))
        ]
        return _result({"Code": 200, "Count": 21, "Data": rows})


class _BeisenTruncatedFirstPageClient(_BeisenPageSizeClient):
    def post_json(self, url, payload, **limits):
        if url.endswith("GetJobAdPageList") and payload["PageSize"] > 20:
            self.posts.append((url, payload, limits))
            return SafeHttpResult(
                status=200,
                final_url=url,
                title="",
                body=b"",
                truncated=True,
            )
        return super().post_json(url, payload, **limits)


class _BeisenEmptyLocationClient(_BeisenClient):
    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        if url.endswith("GetJobAdSearchConditions"):
            return _result(
                {
                    "Code": 200,
                    "Data": [
                        {"Value": "LocId", "Data": []},
                        {"Value": "ClassificationOne", "Data": []},
                    ],
                }
            )
        return _result(
            {
                "Code": 200,
                "Count": 1,
                "Data": [
                    {
                        "JobAdId": 390000001,
                        "JobAdName": "海外销售经理",
                        "CategoryId": "1",
                        "LocNames": [],
                        "ClassificationOne": "营销类",
                    }
                ],
            }
        )


def test_beisen_adapter_accepts_jobs_without_location_labels():
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/social/jobs",
        title="社会招聘",
        body=(
            "<script>BSGlobal = "
            + json.dumps(
                {
                    "Pages": [
                        {
                            "Key": "social-page-id",
                            "PageType": 2,
                            "BusinessType": "1",
                            "Config": "{}",
                        }
                    ]
                }
            )
            + ";</script>"
        ).encode(),
        truncated=False,
    )

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"_max_pages": 2, "_max_opportunities": 20},
        client=_BeisenEmptyLocationClient(),
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert len(result.opportunities) == 1
    assert result.opportunities[0].location_text == "未公开"
    assert result.opportunities[0].city_labels == ()


def test_beisen_adapter_honors_bounded_page_size_override():
    page_config = {
        "Pages": [
            {
                "Key": "campus-page-id",
                "PageType": 2,
                "BusinessType": "2",
                "Config": "{}",
            }
        ]
    }
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/campus/jobs",
        title="校园招聘",
        body=(
            "<script>BSGlobal = "
            + json.dumps(page_config, ensure_ascii=False)
            + ";</script>"
        ).encode(),
        truncated=False,
    )
    client = _BeisenPageSizeClient()

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"page_size": 20, "_max_pages": 10, "_max_opportunities": 100},
        client=client,
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 2
    assert len(result.opportunities) == 21
    jobs_requests = [
        payload
        for url, payload, _limits in client.posts
        if url.endswith("GetJobAdPageList")
    ]
    assert [payload["PageSize"] for payload in jobs_requests] == [20, 20]
    job_limits = [
        limits
        for url, _payload, limits in client.posts
        if url.endswith("GetJobAdPageList")
    ]
    assert all(
        limits["max_response_bytes"] == MAX_LARGE_ADAPTER_RESPONSE_BYTES
        for limits in job_limits
    )


def test_beisen_retries_a_truncated_large_page_with_a_smaller_page_size():
    page_config = {
        "Pages": [
            {
                "Key": "campus-page-id",
                "PageType": 2,
                "BusinessType": "2",
                "Config": "{}",
            }
        ]
    }
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/campus/jobs",
        title="校园招聘",
        body=(
            "<script>BSGlobal = "
            + json.dumps(page_config, ensure_ascii=False)
            + ";</script>"
        ).encode(),
        truncated=False,
    )
    client = _BeisenTruncatedFirstPageClient()

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"page_size": 100, "_max_pages": 5, "_max_opportunities": 100},
        client=client,
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert len(result.opportunities) == 21
    jobs_requests = [
        payload
        for url, payload, _limits in client.posts
        if url.endswith("GetJobAdPageList")
    ]
    assert [payload["PageSize"] for payload in jobs_requests] == [100, 20, 20]


def test_beisen_adapter_uses_large_default_page_size_for_unconfigured_sources():
    page_config = {
        "Pages": [
            {
                "Key": "campus-page-id",
                "PageType": 2,
                "BusinessType": "2",
                "Config": "{}",
            }
        ]
    }
    initial = SafeHttpResult(
        status=200,
        final_url="https://jobs.example.com/campus/jobs",
        title="校园招聘",
        body=(
            "<script>BSGlobal = "
            + json.dumps(page_config, ensure_ascii=False)
            + ";</script>"
        ).encode(),
        truncated=False,
    )
    client = _BeisenPageSizeClient()

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url=initial.final_url,
        config={"_max_pages": 2, "_max_opportunities": 100},
        client=client,
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert len(result.opportunities) == 21
    jobs_requests = [
        payload
        for url, payload, _limits in client.posts
        if url.endswith("GetJobAdPageList")
    ]
    assert [payload["PageSize"] for payload in jobs_requests] == [100]


class _SmicsListClient:
    def __init__(self, second_page: SafeHttpResult):
        self.second_page = second_page
        self.urls = []

    def get(self, url, **limits):
        self.urls.append((url, limits))
        return self.second_page


def _smics_page(page: int, total_pages: int, rows: str) -> SafeHttpResult:
    return SafeHttpResult(
        status=200,
        final_url=f"https://smics.zhiye.com/campus/?PageIndex={page}",
        title="中芯国际校园招聘",
        body=(
            '<div class="zwm"><ul>'
            + rows
            + "</ul></div>"
            + f'<div class="page"><a class="now">{page}</a>'
            + (
                f'<a href="/campus/?PageIndex={page + 1}">下一页</a>'
                if page < total_pages
                else ""
            )
            + f'<a href="/campus/?PageIndex={total_pages}">{total_pages}</a></div>'
        ).encode(),
        truncated=False,
    )


def test_beisen_adapter_parses_smics_server_rendered_list_pagination():
    first = _smics_page(
        1,
        2,
        """
        <li><a href="/campusxq?jobId=390001"><span>技术研发类</span>
          <span>工艺研发工程师（2027届校招）</span><span>硕士</span>
          <span>上海市</span><span>查看职位</span></a></li>
        """,
    )
    second = _smics_page(
        2,
        2,
        """
        <li><a href="/campusxq?jobId=390002"><span>软件算法类</span>
          <span>应用程序开发工程师（2027届校招）</span><span>硕士</span>
          <span>北京市</span><span>查看职位</span></a></li>
        """,
    )
    client = _SmicsListClient(second)

    result = BEISEN_ZHIYE_ADAPTER.collect(
        source_url="https://smics.zhiye.com/campus",
        config={"_max_pages": 10, "_max_opportunities": 100},
        client=client,
        initial_response=first,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 2
    assert [item.title for item in result.opportunities] == [
        "工艺研发工程师（2027届校招）",
        "应用程序开发工程师（2027届校招）",
    ]
    assert result.opportunities[0].recruitment_type == "CAMPUS"
    assert result.opportunities[1].city_labels == ("北京市",)
    assert client.urls[0][0].endswith("/campus/?PageIndex=2")
    assert client.urls[0][1]["max_response_bytes"] == MAX_ADAPTER_RESPONSE_BYTES
