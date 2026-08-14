import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.netease_game import NETEASE_GAME_ADAPTER


def _result(payload, *, url):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _NeteaseGameClient:
    def __init__(self):
        self.gets = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        if "/project/queryOpenList" in url:
            return _result(
                {
                    "code": 200,
                    "data": [
                        {
                            "projectId": 102,
                            "projectName": "网易互娱2027届校园招聘",
                        }
                    ],
                },
                url=url,
            )
        page = len([item for item, _limits in self.gets if "getJobList" in item])
        rows = (
            [
                {
                    "id": 8101,
                    "projectId": 102,
                    "positionName": "AI研究工程师",
                    "positionTypeName": "技术类",
                    "workPlaceName": "杭州, 广州",
                    "positionDescription": "面向2027届毕业生",
                    "positionRequirement": "机器学习相关专业",
                }
            ]
            if page == 1
            else []
        )
        return _result(
            {
                "code": 200,
                "data": {
                    "current": page,
                    "pages": 2,
                    "total": 1,
                    "list": rows,
                },
            },
            url=url,
        )


def _collect(source_url="https://campus.game.163.com/app/job/position?id=102"):
    client = _NeteaseGameClient()
    initial_response = client.get(
        "https://campus.game.163.com/api/campuspc/hy/project/queryOpenList"
    )
    client.gets.clear()
    result = NETEASE_GAME_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=initial_response,
        heartbeat=lambda: None,
    )
    return result, client


def test_netease_game_adapter_collects_only_the_fixed_project():
    result, client = _collect()

    assert result.complete is True
    assert result.category_labels == ("技术类",)
    assert result.city_labels == ("杭州", "广州")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="AI研究工程师",
            target_url=(
                "https://campus.game.163.com/app/detail/index?id=8101&projectId=102"
            ),
            recruitment_type="CAMPUS",
            plan="网易互娱2027届校园招聘",
            location_text="杭州、广州",
            category_labels=("技术类",),
            city_labels=("杭州", "广州"),
            cohort_labels=("2027届",),
        ),
    )
    assert "projectId=102&currentPage=1&pageSize=50" in client.gets[0][0]


def test_netease_game_adapter_rejects_another_project():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        _collect("https://campus.game.163.com/app/job/position?id=75")


def test_netease_game_adapter_rejects_cross_project_rows():
    client = _NeteaseGameClient()
    original_get = client.get

    def get(url, **limits):
        response = original_get(url, **limits)
        if "getJobList" not in url:
            return response
        payload = json.loads(response.body)
        if payload["data"]["list"]:
            payload["data"]["list"][0]["projectId"] = 75
        return _result(payload, url=url)

    client.get = get
    initial_response = original_get(
        "https://campus.game.163.com/api/campuspc/hy/project/queryOpenList"
    )
    client.gets.clear()
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        NETEASE_GAME_ADAPTER.collect(
            source_url="https://campus.game.163.com/app/job/position?id=102",
            config={},
            client=client,
            initial_response=initial_response,
            heartbeat=lambda: None,
        )
