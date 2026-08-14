import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.czbank import CZBANK_ADAPTER
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError


def _result(
    payload, *, url="https://zp.czbank.com.cn/zpweb/planController/getPost.mvc"
):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode("gbk"),
        truncated=False,
    )


class _CzbankClient:
    def __init__(self):
        self.gets = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        page = len(self.gets)
        rows = (
            [
                {
                    "postId": "post-1",
                    "name": "2027届金融科技岗位",
                    "locationName": "杭州、上海",
                    "needOrg": "总行",
                    "needDept": "金融科技部",
                    "majorCond": "计算机相关专业",
                    "vo": {
                        "needPost": "04",
                        "needOrg": "01",
                        "needDept": "02",
                    },
                }
            ]
            if page == 1
            else []
        )
        return _result(
            {"code": "1", "body": [{"postTotalPage": 2, "dataList": rows}]},
            url=url,
        )


def test_czbank_adapter_collects_the_public_paginated_list():
    source_url = (
        "https://zp.czbank.com.cn/zpweb/planController/gotoIndex.mvc?pageType=1"
    )
    client = _CzbankClient()

    result = CZBANK_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "浙商银行招聘", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ()
    assert result.city_labels == ("杭州", "上海")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="2027届金融科技岗位",
            target_url=(
                "https://zp.czbank.com.cn/zpweb/zpPostController/"
                "jobDetailPage.mvc?postId=post-1"
            ),
            recruitment_type="CAMPUS",
            plan="校园招聘",
            location_text="杭州、上海",
            category_labels=(),
            city_labels=("杭州", "上海"),
            cohort_labels=("2027届",),
        ),
    )
    assert "start=0&end=6" in client.gets[0][0]
    assert "start=6&end=12" in client.gets[1][0]


def test_czbank_adapter_accepts_the_current_authoritative_empty_list():
    client = _CzbankClient()
    client.get = lambda url, **limits: _result(
        {"code": "1", "body": [{"postTotalPage": 0, "dataList": []}]},
        url=url,
    )

    result = CZBANK_ADAPTER.collect(
        source_url=(
            "https://zp.czbank.com.cn/zpweb/planController/gotoIndex.mvc?pageType=1"
        ),
        config={},
        client=client,
        initial_response=SafeHttpResult(
            200, "https://zp.czbank.com.cn", "", b"", False
        ),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.opportunities == ()


def test_czbank_adapter_rejects_non_campus_source_urls():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        CZBANK_ADAPTER.collect(
            source_url=(
                "https://zp.czbank.com.cn/zpweb/planController/gotoIndex.mvc?pageType=2"
            ),
            config={},
            client=_CzbankClient(),
            initial_response=SafeHttpResult(
                200, "https://zp.czbank.com.cn", "", b"", False
            ),
            heartbeat=lambda: None,
        )
