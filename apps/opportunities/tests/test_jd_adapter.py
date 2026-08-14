import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.jd import JD_CAMPUS_ADAPTER


def _result(payload, *, url):
    return SafeHttpResult(
        200,
        url,
        "",
        json.dumps(payload, ensure_ascii=False).encode(),
        False,
    )


def _projects():
    return _result(
        {
            "success": True,
            "body": {
                "projectList": [
                    {
                        "type": "实习生",
                        "code": "internship",
                        "groupList": [
                            {
                                "name": "JD YOUNG-实习生计划",
                                "planMapList": [
                                    {"id": 45, "planName": "JD YOUNG-实习生计划"}
                                ],
                            }
                        ],
                    }
                ]
            },
        },
        url="https://campus.jd.com/api/wx/position/getProjectList",
    )


class _JdClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        page = payload["pageIndex"]
        rows = (
            [
                {
                    "publishId": 4864,
                    "reqId": 1581,
                    "positionName": "算法工程师-语言大模型",
                    "jobDirection": "技术方向",
                    "workContent": "参与自然语言处理研发",
                    "qualification": "面向27届在校生",
                    "requirementVoList": [
                        {"workCity": "浙江省-杭州市"},
                        {"workCity": "上海市-上海市"},
                        {"workCity": "浙江省-杭州市"},
                    ],
                }
            ]
            if page == 0
            else []
        )
        return _result(
            {"success": True, "body": {"totalNumber": 1, "items": rows}},
            url=url,
        )


class _SplitJdClient(_JdClient):
    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        page_size = payload["pageSize"]
        page = payload["pageIndex"]
        if page_size == 5:
            return SafeHttpResult(200, url, "", b"{" * 262_144, True)
        row = {
            "publishId": 9000 + page,
            "reqId": 8000 + page,
            "positionName": f"拆分岗位{page}",
            "jobDirection": "技术方向",
            "workContent": "研发",
            "qualification": "面向27届",
            "requirementVoList": [{"workCity": "浙江省-杭州市"}],
        }
        return _result(
            {"success": True, "body": {"totalNumber": 5, "items": [row]}},
            url=url,
        )


def test_jd_adapter_collects_the_fixed_internship_project():
    client = _JdClient()
    result = JD_CAMPUS_ADAPTER.collect(
        source_url="https://campus.jd.com/#/jobs?selProjects=45",
        config={},
        client=client,
        initial_response=_projects(),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("技术方向",)
    assert result.city_labels == ("杭州市", "上海市")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="算法工程师-语言大模型",
            target_url="https://campus.jd.com/#/details?id=4864",
            recruitment_type="INTERNSHIP",
            plan="JD YOUNG-实习生计划",
            location_text="浙江省-杭州市、上海市-上海市",
            category_labels=("技术方向",),
            city_labels=("杭州市", "上海市"),
            cohort_labels=("2027届",),
        ),
    )
    assert client.posts[0] == (
        "https://campus.jd.com/api/wx/position/page?type=present",
        {
            "pageSize": 5,
            "pageIndex": 0,
            "parameter": {
                "positionName": "",
                "planIdList": ["45"],
                "jobDirectionCodeList": [],
                "workCityCodeList": [],
                "positionDeptList": [],
            },
        },
        {"max_response_bytes": 262_144},
    )


def test_jd_adapter_rejects_a_source_for_another_project():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        JD_CAMPUS_ADAPTER.source_probe_url(
            "https://campus.jd.com/#/jobs?selProjects=56"
        )


def test_jd_adapter_rejects_when_project_45_is_no_longer_published():
    response = _result(
        {"success": True, "body": {"projectList": []}},
        url="https://campus.jd.com/api/wx/position/getProjectList",
    )
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        JD_CAMPUS_ADAPTER.collect(
            source_url="https://campus.jd.com/#/jobs?selProjects=45",
            config={},
            client=_JdClient(),
            initial_response=response,
            heartbeat=lambda: None,
        )


def test_jd_adapter_splits_an_oversized_page_into_bounded_single_jobs():
    client = _SplitJdClient()

    result = JD_CAMPUS_ADAPTER.collect(
        source_url="https://campus.jd.com/#/jobs?selProjects=45",
        config={"_max_pages": 10},
        client=client,
        initial_response=_projects(),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert len(result.opportunities) == 5
    assert result.pages_read == 6
    assert [call[1]["pageSize"] for call in client.posts] == [5, 1, 1, 1, 1, 1]
    assert all(call[2] == {"max_response_bytes": 393_216} for call in client.posts[1:])
