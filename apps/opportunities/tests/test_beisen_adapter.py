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
