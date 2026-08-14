import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.antgroup import ANTGROUP_ADAPTER
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError


def _result(payload, *, url):
    return SafeHttpResult(
        200, url, "", json.dumps(payload, ensure_ascii=False).encode(), False
    )


class _AntClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        if "/searchCondition/list" in url:
            return _result(
                {
                    "success": True,
                    "content": {
                        "searchItems": [
                            {
                                "type": "recruitType",
                                "items": [
                                    {
                                        "label": "应届生招聘",
                                        "value": "campus_graduates",
                                        "children": [
                                            {
                                                "label": "蚂蚁集团2027届应届生招聘",
                                                "value": "26070900089909",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                        "totalPositions": 1,
                    },
                },
                url=url,
            )
        page = payload["pageIndex"]
        rows = (
            [
                {
                    "id": 260721011006030,
                    "name": "智能体与大模型应用工程",
                    "workLocations": ["北京", "杭州"],
                    "categoryName": "技术类",
                    "batchId": 26070900089909,
                    "batchName": "蚂蚁集团2027届应届生招聘",
                    "batchType": "graduate",
                }
            ]
            if page == 1
            else []
        )
        return _result(
            {
                "success": True,
                "errorCode": "success",
                "content": rows,
                "totalCount": 1,
                "pageSize": 5,
                "currentPage": page,
            },
            url=url,
        )


def test_antgroup_adapter_discovers_current_graduate_batches_and_collects_jobs():
    client = _AntClient()
    source_url = "https://talent.antgroup.com/campus-full-list?type=campus_graduates"
    result = ANTGROUP_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "蚂蚁集团", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("技术类",)
    assert result.city_labels == ("北京", "杭州")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="智能体与大模型应用工程",
            target_url="https://talent.antgroup.com/campus-position?positionId=260721011006030",
            recruitment_type="CAMPUS",
            plan="蚂蚁集团2027届应届生招聘",
            location_text="北京、杭州",
            category_labels=("技术类",),
            city_labels=("北京", "杭州"),
            cohort_labels=("2027届",),
        ),
    )
    assert client.posts[1][1]["batchIds"] == ["26070900089909"]
    assert client.posts[1][1]["pageSize"] == 5


def test_antgroup_adapter_rejects_missing_graduate_batch_group():
    client = _AntClient()
    original_post = client.post_json

    def post_json(url, payload, **limits):
        response = original_post(url, payload, **limits)
        if "/searchCondition/list" in url:
            return _result({"success": True, "content": {"searchItems": []}}, url=url)
        return response

    client.post_json = post_json
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        ANTGROUP_ADAPTER.collect(
            source_url="https://talent.antgroup.com/campus-full-list?type=campus_graduates",
            config={},
            client=client,
            initial_response=SafeHttpResult(
                200, "https://talent.antgroup.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )


def test_antgroup_adapter_rejects_another_source_type():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        ANTGROUP_ADAPTER.collect(
            source_url="https://talent.antgroup.com/campus-full-list?type=campus_intern",
            config={},
            client=_AntClient(),
            initial_response=SafeHttpResult(
                200, "https://talent.antgroup.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )
