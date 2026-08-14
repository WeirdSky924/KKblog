import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.tencent import TENCENT_ADAPTER


def _result(payload, *, url):
    return SafeHttpResult(
        200, url, "", json.dumps(payload, ensure_ascii=False).encode(), False
    )


class _TencentClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        page = payload["pageIndex"]
        rows = (
            [
                {
                    "id": 21417,
                    "position": 101,
                    "positionTitle": "后台开发",
                    "positionFamily": 2,
                    "projectId": 2,
                    "workCities": "深圳总部 北京 杭州 ",
                    "projectName": "应届实习",
                    "recruitLabelName": "应届实习",
                    "postId": "1200791473415778304",
                }
            ]
            if page == 1
            else []
        )
        return _result(
            {"message": "", "status": 0, "data": {"positionList": rows, "count": 1}},
            url=url,
        )


def test_tencent_adapter_collects_the_fixed_internship_listing():
    client = _TencentClient()
    source_url = "https://join.qq.com/post.html?query=p_2"
    result = TENCENT_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "岗位投递", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("技术类",)
    assert result.city_labels == ("深圳总部", "北京", "杭州")
    assert result.opportunities == (
        CollectedOpportunity(
            title="后台开发",
            target_url="https://join.qq.com/post_detail.html?postid=1200791473415778304",
            recruitment_type="INTERNSHIP",
            plan="应届实习",
            location_text="深圳总部、北京、杭州",
            category_labels=("技术类",),
            city_labels=("深圳总部", "北京", "杭州"),
            cohort_labels=(),
        ),
    )
    assert client.posts[0][1]["projectMappingIdList"] == [2]
    assert client.posts[0][1]["pageSize"] == 100


def test_tencent_adapter_rejects_another_project_query():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        TENCENT_ADAPTER.collect(
            source_url="https://join.qq.com/post.html?query=p_1",
            config={},
            client=_TencentClient(),
            initial_response=SafeHttpResult(200, "https://join.qq.com", "", b"", False),
            heartbeat=lambda: None,
        )


def test_tencent_adapter_keeps_official_rows_without_an_optional_family():
    client = _TencentClient()
    original_post = client.post_json

    def post_json(url, payload, **limits):
        response = original_post(url, payload, **limits)
        body = json.loads(response.body)
        body["data"]["positionList"][0]["positionFamily"] = None
        return _result(body, url=url)

    client.post_json = post_json
    result = TENCENT_ADAPTER.collect(
        source_url="https://join.qq.com/post.html?query=p_2",
        config={},
        client=client,
        initial_response=SafeHttpResult(200, "https://join.qq.com", "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.opportunities[0].category_labels == ()


def test_tencent_adapter_rejects_rows_from_another_project():
    client = _TencentClient()
    original_post = client.post_json

    def post_json(url, payload, **limits):
        response = original_post(url, payload, **limits)
        body = json.loads(response.body)
        if body["data"]["positionList"]:
            body["data"]["positionList"][0]["projectId"] = 99
        return _result(body, url=url)

    client.post_json = post_json
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        TENCENT_ADAPTER.collect(
            source_url="https://join.qq.com/post.html?query=p_2",
            config={},
            client=client,
            initial_response=SafeHttpResult(200, "https://join.qq.com", "", b"", False),
            heartbeat=lambda: None,
        )
