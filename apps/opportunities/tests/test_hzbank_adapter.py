import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.hzbank import HZBANK_ADAPTER


def _result(payload, *, url="https://myjob.hzbank.com.cn/hzzp-apply/api"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _HzbankClient:
    def __init__(self):
        self.gets = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        page = 0 if "page=0" in url else 1
        rows = (
            [
                {
                    "id": "position-1",
                    "positionName": "2027届金融科技培训生",
                    "workSpace": "杭州,上海",
                    "positionCategoryName": "科技",
                    "organizationName": "总行",
                    "jobDesc": "面向27届毕业生。",
                    "jobRequire": "计算机相关专业。",
                }
            ]
            if page == 0
            else []
        )
        return _result(
            {
                "errorCode": "0",
                "result": {
                    "content": rows,
                    "totalElements": 1,
                    "totalPages": 1,
                    "number": page,
                },
            },
            url=url,
        )

    def post_json(self, url, payload, **limits):
        raise AssertionError("杭州银行公开岗位列表使用 GET")


@pytest.mark.parametrize(
    ("source_url", "position_type", "recruitment_type", "plan"),
    (
        (
            "https://myjob.hzbank.com.cn/hzzp-apply-web/static/"
            "index.html#/employ/school",
            "01",
            "CAMPUS",
            "校园招聘",
        ),
        (
            "https://myjob.hzbank.com.cn/hzzp-apply-web/static/"
            "index.html#/employ/ungraduate",
            "03",
            "INTERNSHIP",
            "实习招聘",
        ),
    ),
)
def test_hzbank_adapter_collects_the_public_paginated_list(
    source_url, position_type, recruitment_type, plan
):
    client = _HzbankClient()

    result = HZBANK_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "杭州银行招聘", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("科技",)
    assert result.city_labels == ("杭州", "上海")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="2027届金融科技培训生",
            target_url=(
                "https://myjob.hzbank.com.cn/hzzp-apply-web/static/"
                "index.html#/employDesc/position-1"
            ),
            recruitment_type=recruitment_type,
            plan=plan,
            location_text="杭州、上海",
            category_labels=("科技",),
            city_labels=("杭州", "上海"),
            cohort_labels=("2027届",),
        ),
    )
    assert f"positionType={position_type}" in client.gets[0][0]


def test_hzbank_adapter_accepts_an_authoritative_empty_list():
    client = _HzbankClient()
    client.get = lambda url, **limits: _result(
        {
            "errorCode": "0",
            "result": {
                "content": [],
                "totalElements": 0,
                "totalPages": 0,
                "number": 0,
            },
        },
        url=url,
    )

    result = HZBANK_ADAPTER.collect(
        source_url=(
            "https://myjob.hzbank.com.cn/hzzp-apply-web/static/"
            "index.html#/employ/school"
        ),
        config={},
        client=client,
        initial_response=SafeHttpResult(
            200, "https://myjob.hzbank.com.cn", "", b"", False
        ),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.opportunities == ()


def test_hzbank_adapter_rejects_an_unknown_source_route():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        HZBANK_ADAPTER.collect(
            source_url=(
                "https://myjob.hzbank.com.cn/hzzp-apply-web/static/"
                "index.html#/employ/social"
            ),
            config={},
            client=_HzbankClient(),
            initial_response=SafeHttpResult(
                200, "https://myjob.hzbank.com.cn", "", b"", False
            ),
            heartbeat=lambda: None,
        )
