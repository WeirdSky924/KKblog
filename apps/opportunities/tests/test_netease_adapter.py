import json

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult
from apps.opportunities.checks.netease import NETEASE_HR_ADAPTER


def _result(payload, *, url="https://hr.163.com/api/hr163/position/queryPage"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _NeteaseClient:
    def __init__(self):
        self.gets = []
        self.posts = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        return _result(
            {
                "code": 200,
                "data": {
                    "id": 78139,
                    "name": "内容传播实习生",
                },
            },
            url=url,
        )

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        page = payload["currentPage"]
        rows = (
            [
                {
                    "id": 78139,
                    "name": "内容传播实习生（网易千千壁纸）",
                    "workType": "1",
                    "firstPostTypeName": "市场",
                    "workPlaceNameList": ["广州市"],
                    "requirement": "每周工作不少于4天。",
                    "description": "负责内容合作。",
                }
            ]
            if page == 1
            else [
                {
                    "id": 78140,
                    "name": "游戏系统策划实习生（2027届）",
                    "workType": "1",
                    "firstPostTypeName": "产品",
                    "workPlaceNameList": ["杭州市", "上海市"],
                    "requirement": "面向27届毕业生。",
                    "description": "负责游戏系统设计。",
                }
            ]
        )
        return _result(
            {
                "code": 200,
                "data": {
                    "pages": 2,
                    "total": 2,
                    "list": rows,
                },
            }
        )


def test_netease_adapter_collects_all_pages_and_filter_options():
    source_url = "https://hr.163.com/job-list.html?workType=1"
    client = _NeteaseClient()

    result = NETEASE_HR_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "网易招聘", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 2
    assert result.category_labels == ("市场", "产品")
    assert result.city_labels == ("广州市", "杭州市", "上海市")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="内容传播实习生（网易千千壁纸）",
            target_url="https://hr.163.com/job-detail.html?id=78139",
            recruitment_type="INTERNSHIP",
            plan="实习招聘",
            location_text="广州市",
            category_labels=("市场",),
            city_labels=("广州市",),
            cohort_labels=(),
        ),
        CollectedOpportunity(
            title="游戏系统策划实习生（2027届）",
            target_url="https://hr.163.com/job-detail.html?id=78140",
            recruitment_type="INTERNSHIP",
            plan="实习招聘",
            location_text="杭州市、上海市",
            category_labels=("产品",),
            city_labels=("杭州市", "上海市"),
            cohort_labels=("2027届",),
        ),
    )
    assert [request[1] for request in client.posts] == [
        {"currentPage": 1, "pageSize": 10, "workType": 1},
        {"currentPage": 2, "pageSize": 10, "workType": 1},
    ]


def test_netease_adapter_uses_public_position_detail_probe():
    source_url = "https://hr.163.com/job-list.html?workType=1"
    target_url = "https://hr.163.com/job-detail.html?id=78139"
    client = _NeteaseClient()

    response = NETEASE_HR_ADAPTER.check_opportunity(
        source_url=source_url,
        target_url=target_url,
        config={},
        client=client,
    )

    assert response.status == 200
    assert client.gets == [("https://hr.163.com/api/hr163/position/query?id=78139", {})]
