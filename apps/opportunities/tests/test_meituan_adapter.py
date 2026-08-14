import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.meituan import MEITUAN_ADAPTER


def _result(payload, *, url):
    return SafeHttpResult(
        200,
        url,
        "",
        json.dumps(payload, ensure_ascii=False).encode(),
        False,
    )


class _MeituanClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        page = payload["page"]["pageNo"]
        rows = (
            [
                {
                    "jobUnionId": "4683995941",
                    "name": "大模型算法工程师",
                    "projectName": "2027届北斗计划",
                    "jobType": "1",
                    "jobFamily": "技术类",
                    "jobFamilyGroup": "算法",
                    "cityList": [{"name": "北京市"}, {"name": "杭州市"}],
                    "jobDuty": "参与大模型后训练",
                    "jobRequirement": "2027届本科及以上学历",
                }
            ]
            if page == 1
            else []
        )
        return _result(
            {
                "message": "成功",
                "data": {
                    "list": rows,
                    "page": {
                        "pageNo": page,
                        "pageSize": 5,
                        "totalPage": 2,
                        "totalCount": 1,
                    },
                },
            },
            url=url,
        )


def test_meituan_adapter_collects_the_fixed_campus_listing():
    client = _MeituanClient()
    source_url = "https://zhaopin.meituan.com/web/position?hiringType=4_1"

    result = MEITUAN_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "美团招聘", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("算法",)
    assert result.city_labels == ("北京市", "杭州市")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="大模型算法工程师",
            target_url=(
                "https://zhaopin.meituan.com/web/position/detail?"
                "jobUnionId=4683995941&highlightType=campus"
            ),
            recruitment_type="CAMPUS",
            plan="2027届北斗计划",
            location_text="北京市、杭州市",
            category_labels=("算法",),
            city_labels=("北京市", "杭州市"),
            cohort_labels=("2027届",),
        ),
    )
    assert client.posts[0][1] == {
        "page": {"pageNo": 1, "pageSize": 5},
        "jobShareType": "1",
        "keywords": "",
        "cityList": [],
        "department": [],
        "jfJgList": [],
        "jobType": [{"code": "4", "subCode": ["1"]}],
        "typeCode": ["1"],
        "specialCode": [],
    }


def test_meituan_adapter_rejects_another_hiring_type():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        MEITUAN_ADAPTER.collect(
            source_url="https://zhaopin.meituan.com/web/position?hiringType=2_6",
            config={},
            client=_MeituanClient(),
            initial_response=SafeHttpResult(
                200, "https://zhaopin.meituan.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )


def test_meituan_adapter_rejects_inconsistent_pagination():
    client = _MeituanClient()
    original_post = client.post_json

    def post_json(url, payload, **limits):
        response = original_post(url, payload, **limits)
        body = json.loads(response.body)
        body["data"]["page"]["totalCount"] = 2 if payload["page"]["pageNo"] == 1 else 3
        return _result(body, url=url)

    client.post_json = post_json
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        MEITUAN_ADAPTER.collect(
            source_url="https://zhaopin.meituan.com/web/position?hiringType=4_1",
            config={},
            client=client,
            initial_response=SafeHttpResult(
                200, "https://zhaopin.meituan.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )


def test_meituan_adapter_deduplicates_identical_official_rows():
    client = _MeituanClient()
    original_post = client.post_json

    def post_json(url, payload, **limits):
        response = original_post(url, payload, **limits)
        body = json.loads(response.body)
        if payload["page"]["pageNo"] == 1:
            body["data"]["list"].append(dict(body["data"]["list"][0]))
            body["data"]["page"]["totalCount"] = 2
            body["data"]["page"]["totalPage"] = 1
        return _result(body, url=url)

    client.post_json = post_json
    result = MEITUAN_ADAPTER.collect(
        source_url="https://zhaopin.meituan.com/web/position?hiringType=4_1",
        config={},
        client=client,
        initial_response=SafeHttpResult(
            200, "https://zhaopin.meituan.com", "", b"", False
        ),
        heartbeat=lambda: None,
    )

    assert len(result.opportunities) == 1
