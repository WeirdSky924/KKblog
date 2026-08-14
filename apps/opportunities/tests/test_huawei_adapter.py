import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.huawei import HUAWEI_ADAPTER


def _result(payload, *, url):
    return SafeHttpResult(
        200,
        url,
        "",
        json.dumps(payload, ensure_ascii=False).encode(),
        False,
    )


class _HuaweiClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        page = payload["curPage"]
        rows = (
            [
                {
                    "advertisementsIntegrationId": 219745,
                    "advertisementId": 36385,
                    "jobId": 103902,
                    "jobName": "算法工程师",
                    "workPlace": "苏州/杭州/北京",
                    "categoryName": "研发类",
                    "scenarioName": "应届生",
                }
            ]
            if page == 1
            else []
        )
        return _result(
            {
                "status": "SUCCESS",
                "data": {
                    "pageVO": {
                        "totalRows": 1,
                        "curPage": page,
                        "pageSize": 10,
                        "totalPages": 2,
                    },
                    "result": rows,
                },
                "errors": None,
            },
            url=url,
        )


def test_huawei_adapter_collects_the_fixed_fresh_graduate_listing():
    client = _HuaweiClient()
    source_url = (
        "https://career.huawei.com/cn/campus-recruitment-job-list?"
        "recruitmentType=FRESH_GRADUATE"
    )

    result = HUAWEI_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "校招职位列表", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("研发类",)
    assert result.city_labels == ("苏州", "杭州", "北京")
    assert result.opportunities == (
        CollectedOpportunity(
            title="算法工程师",
            target_url="https://career.huawei.com/cn/job-details?advertisementId=36385",
            recruitment_type="CAMPUS",
            plan="应届生",
            location_text="苏州、杭州、北京",
            category_labels=("研发类",),
            city_labels=("苏州", "杭州", "北京"),
            cohort_labels=(),
        ),
    )
    assert client.posts[0][0].startswith(
        "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/"
    )
    assert client.posts[0][1] == {
        "curPage": 1,
        "pageSize": 10,
        "jobType": "CR",
        "recruitmentType": ["FRESH_GRADUATE"],
    }
    assert client.posts[0][2]["headers"] == {
        "Origin": "https://career.huawei.com",
        "Referer": "https://career.huawei.com/",
        "X-Jalor-TenantAlias": "hcm",
        "X-HW-ID": "app_000000035886",
        "X-Referer": "https://career.huawei.com/cn",
    }


def test_huawei_adapter_rejects_another_recruitment_type():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        HUAWEI_ADAPTER.collect(
            source_url=(
                "https://career.huawei.com/cn/campus-recruitment-job-list?"
                "recruitmentType=INTERN"
            ),
            config={},
            client=_HuaweiClient(),
            initial_response=SafeHttpResult(
                200, "https://career.huawei.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )


def test_huawei_adapter_rejects_inconsistent_pagination():
    client = _HuaweiClient()
    original_post = client.post_json

    def post_json(url, payload, **limits):
        response = original_post(url, payload, **limits)
        body = json.loads(response.body)
        body["data"]["pageVO"]["totalRows"] = 2 if payload["curPage"] == 1 else 3
        return _result(body, url=url)

    client.post_json = post_json
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        HUAWEI_ADAPTER.collect(
            source_url=(
                "https://career.huawei.com/cn/campus-recruitment-job-list?"
                "recruitmentType=FRESH_GRADUATE"
            ),
            config={},
            client=client,
            initial_response=SafeHttpResult(
                200, "https://career.huawei.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )
