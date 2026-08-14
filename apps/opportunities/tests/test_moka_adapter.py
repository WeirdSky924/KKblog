import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.moka import MOKA_ADAPTER, _job, _source_config

_ENCRYPTED_PAGE = (
    "56KRs+6L4cMxm6LPDTGQzkNIOCkeFwu7f3fEYIOch5Ysy9zDWuqqtxuEA2ssBkEK"
    "Abl7JNtJVhY9eQoTk4eXua6uFv66dbc+5gcosPqlikSqkqtpqsxVP4m0ds74QoH9"
    "awxeByFym/P+Q8wjvNVwaCZVfGLvEC84ahcuGKEW0MggEYG+QaW3lZmm8vkzlVh"
    "c2demYJRRkf57gb/e5lmTePMFQUNUqJdRPSe/hRZ8F037+gu+YqDOSk0dwMOGMHm"
    "VvKUfIsu1fIhxHnb97ooqWDgsgfDSexsghTIB7qCmL5ONnYAHjDuNMPlq5tzMie"
    "cpp89rEMtrX+02gfsi5LgHGw=="
)
_ENCRYPTED_DETAIL = (
    "56KRs+6L4cMxm6LPDTGQzkNIOCkeFwu7f3fEYIOch5azdlFmLqsQKXzcU00vpF9j"
    "9giQHBLOJyEa9AKdjLaDWQwP1QYnXyFTP1fzYr0W1IqLzTo1E4eWsGn0mtBOAYpY"
)


def _result(payload, *, url="https://app.mokahr.com/api"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _MokaClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        if url.endswith("/website/job"):
            return _result(
                {
                    "data": _ENCRYPTED_DETAIL,
                    "necromancer": "0123456789abcdef",
                }
            )
        if url.endswith("filterFieldsAggregations"):
            return _result(
                {
                    "code": 0,
                    "success": True,
                    "data": {
                        "systemFieldsAggregations": {
                            "commitmentAggregation": {
                                "commitmentList": ["全职", "实习"]
                            },
                            "locationAggregation": {
                                "locationList": [
                                    {
                                        "id": "杭州市",
                                        "label": "杭州市",
                                        "locationRows": [{"id": 47537}],
                                    }
                                ]
                            },
                            "zhinengAggregation": {
                                "zhinengList": [
                                    {"id": 12, "label": "研发类", "jobCount": 1}
                                ]
                            },
                        }
                    },
                }
            )
        return _result(
            {
                "data": _ENCRYPTED_PAGE,
                "necromancer": "0123456789abcdef",
            }
        )


def test_moka_adapter_collects_filtered_jobs_and_filter_options():
    source_url = (
        "https://app.mokahr.com/campus-recruitment/demo/147434?locale=zh-CN"
        "#/jobs?zhineng%5B0%5D=12&commitment%5B0%5D=%E5%AE%9E%E4%B9%A0"
    )
    client = _MokaClient()
    heartbeats = []

    result = MOKA_ADAPTER.collect(
        source_url=source_url,
        config={"aes_iv": "fedcba9876543210"},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "招聘", b"", True),
        heartbeat=lambda: heartbeats.append(True),
    )

    assert result.complete is True
    assert result.pages_read == 1
    assert result.category_labels == ("研发类",)
    assert result.city_labels == ("杭州市",)
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="AI开发工程师（27届）",
            target_url=(
                "https://app.mokahr.com/campus-recruitment/demo/147434"
                "?locale=zh-CN#/job/job-1"
            ),
            recruitment_type="INTERNSHIP",
            plan="实习招聘",
            location_text="浙江·西湖区",
            category_labels=("研发类",),
            city_labels=("杭州市",),
            cohort_labels=("2027届",),
        ),
    )
    assert client.posts[0][1] == {
        "zhinengIds": ["12"],
        "orgId": "demo",
        "siteId": 147434,
        "locale": "zh-CN",
    }
    assert client.posts[1][1]["commitments"] == ["实习"]
    assert client.posts[1][1]["zhinengIds"] == ["12"]
    assert client.posts[1][1]["limit"] == 30
    assert heartbeats


def test_moka_adapter_rejects_invalid_encryption_config():
    source_url = "https://app.mokahr.com/social-recruitment/demo/45487#/jobs"

    with pytest.raises(SafeRequestError) as error:
        MOKA_ADAPTER.collect(
            source_url=source_url,
            config={"aes_iv": "short"},
            client=_MokaClient(),
            initial_response=SafeHttpResult(200, source_url, "招聘", b"", False),
            heartbeat=lambda: None,
        )

    assert error.value.error_code == "opportunities.adapter_config_invalid.v1"


def test_moka_adapter_accepts_a_bounded_page_size_for_large_job_bodies():
    client = _MokaClient()

    MOKA_ADAPTER.collect(
        source_url="https://app.mokahr.com/social-recruitment/demo/45487#/jobs",
        config={
            "aes_iv": "fedcba9876543210",
            "page_size": 10,
            "_max_pages": 100,
        },
        client=client,
        initial_response=SafeHttpResult(200, "https://app.mokahr.com", "", b"", False),
        heartbeat=lambda: None,
    )

    assert client.posts[1][1]["limit"] == 10


@pytest.mark.parametrize("page_size", (0, 31, True, "10"))
def test_moka_adapter_rejects_an_invalid_page_size(page_size):
    with pytest.raises(SafeRequestError) as error:
        MOKA_ADAPTER.collect(
            source_url="https://app.mokahr.com/social-recruitment/demo/45487#/jobs",
            config={"aes_iv": "fedcba9876543210", "page_size": page_size},
            client=_MokaClient(),
            initial_response=SafeHttpResult(
                200, "https://app.mokahr.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )

    assert error.value.error_code == "opportunities.adapter_config_invalid.v1"


def test_moka_adapter_uses_small_source_and_detail_health_probes():
    source_url = "https://app.mokahr.com/social-recruitment/demo/45487#/jobs"
    target_url = "https://app.mokahr.com/social-recruitment/demo/45487#/job/job-1"
    client = _MokaClient()

    assert MOKA_ADAPTER.source_probe_url(source_url) == (
        "https://app.mokahr.com/api/env"
    )
    response = MOKA_ADAPTER.check_opportunity(
        source_url=source_url,
        target_url=target_url,
        config={"aes_iv": "fedcba9876543210"},
        client=client,
    )

    assert response.status == 200
    assert client.posts == [
        (
            "https://app.mokahr.com/api/outer/ats-apply/website/job",
            {
                "siteId": 45487,
                "orgId": "demo",
                "jobId": "job-1",
                "locale": "zh-CN",
            },
            {"max_response_bytes": 65_536},
        )
    ]


def test_moka_job_allows_an_open_position_without_published_locations():
    source = _source_config(
        "https://app.mokahr.com/campus-recruitment/demo/147434#/jobs"
    )

    item = _job(
        {
            "id": "job-without-location",
            "title": "软件测试工程师",
            "status": "open",
            "commitment": "全职",
            "locations": [],
            "zhineng": {"id": 12, "name": "研发类"},
        },
        source=source,
        filtered_commitments=(),
        location_map={},
    )

    assert item.location_text == "未公开"
    assert item.city_labels == ()
