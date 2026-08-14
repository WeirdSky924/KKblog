import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.getui import GETUI_ADAPTER
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError


def _result(payload, *, url="https://job.getui.com/data/recruit/school/2021/job/list"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _GetuiClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        return _result(
            {
                "errNo": 0,
                "data": {
                    "total": 2,
                    "list": [
                        {
                            "id": 226,
                            "name": "AI算法工程师（数智菁英计划）",
                            "city": "浙江省/杭州市",
                            "type": "算法类",
                            "content": "负责大模型研发。",
                        },
                        {
                            "id": 239,
                            "name": "AI算法工程师（实习）",
                            "city": "浙江省/杭州市",
                            "type": "算法类",
                            "content": "负责算法实习工作。",
                        },
                    ],
                },
            },
            url=url,
        )


def test_getui_adapter_collects_the_category_selected_by_the_source_url():
    source_url = "https://job.getui.com/campus/position/226?type=算法类"
    client = _GetuiClient()

    result = GETUI_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "每日互动招聘", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("算法类",)
    assert result.city_labels == ("浙江省", "杭州市")
    assert result.opportunities == (
        CollectedOpportunity(
            title="AI算法工程师（数智菁英计划）",
            target_url="https://job.getui.com/campus/position/226?type=%E7%AE%97%E6%B3%95%E7%B1%BB",
            recruitment_type="CAMPUS",
            plan="校园招聘",
            location_text="浙江省、杭州市",
            category_labels=("算法类",),
            city_labels=("浙江省", "杭州市"),
            cohort_labels=(),
        ),
        CollectedOpportunity(
            title="AI算法工程师（实习）",
            target_url="https://job.getui.com/campus/position/239?type=%E7%AE%97%E6%B3%95%E7%B1%BB",
            recruitment_type="INTERNSHIP",
            plan="实习招聘",
            location_text="浙江省、杭州市",
            category_labels=("算法类",),
            city_labels=("浙江省", "杭州市"),
            cohort_labels=(),
        ),
    )
    assert client.posts == [
        (
            "https://job.getui.com/data/recruit/school/2021/job/list",
            {"pageNum": 1, "pageSize": 100, "typeList": ["算法类"]},
            {},
        )
    ]


def test_getui_adapter_rejects_a_mismatched_category_anchor():
    source_url = "https://job.getui.com/campus/position/192?type=算法类"

    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        GETUI_ADAPTER.collect(
            source_url=source_url,
            config={},
            client=_GetuiClient(),
            initial_response=SafeHttpResult(
                200, source_url, "每日互动招聘", b"", False
            ),
            heartbeat=lambda: None,
        )


def test_getui_adapter_rejects_an_unknown_source_url():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        GETUI_ADAPTER.collect(
            source_url="https://job.getui.com/society/position/226?type=算法类",
            config={},
            client=_GetuiClient(),
            initial_response=SafeHttpResult(
                200, "https://job.getui.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )
