import json

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult
from apps.opportunities.checks.leihuo import NETEASE_LEIHUO_ADAPTER


def _result(payload, *, url="https://xiaozhao.leihuo.netease.com/api"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _LeihuoClient:
    def __init__(self):
        self.gets = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        if "filter/show" in url:
            return _result(
                {
                    "status": 200,
                    "msg": "success",
                    "data": {
                        "simple": {
                            "job_apply_work_place": {
                                "title": "工作城市",
                                "data": [{"key": "杭州", "name": "杭州"}],
                            },
                            "job_apply_category": {
                                "title": "职位类别",
                                "data": [{"key": 3, "name": "人工智能"}],
                            },
                        }
                    },
                }
            )
        if "detail/show" in url:
            return _result(
                {"status": 200, "msg": "success", "data": {"ehr_job_id": "3738"}}
            )
        return _result(
            {
                "status": 200,
                "msg": "success",
                "data": {
                    "count_number": 1,
                    "last_page": True,
                    "pages_count": 1,
                    "apply_job_list": [
                        {
                            "job_code": "PO1000087",
                            "job_name": "人工智能算法工程师（Agent方向）",
                            "ehr_job_id": "3738",
                            "ehr_project_id": "77",
                            "job_target": "2027届应届毕业生",
                            "type_name": "全职",
                            "category_name": "人工智能",
                            "work_place_name": "杭州",
                            "job_detail_url": (
                                "https://campus.163.com/app/detail/index"
                                "?id=3738&projectId=77"
                            ),
                        }
                    ],
                },
            }
        )


def test_leihuo_adapter_collects_project_jobs_and_filters():
    source_url = "https://leihuo.163.com/campus/#/full?channel=test"
    client = _LeihuoClient()

    result = NETEASE_LEIHUO_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "雷火", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.category_labels == ("人工智能",)
    assert result.city_labels == ("杭州",)
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="人工智能算法工程师（Agent方向）",
            target_url=("https://campus.163.com/app/detail/index?id=3738&projectId=77"),
            recruitment_type="CAMPUS",
            plan="27届校园招聘",
            location_text="杭州",
            category_labels=("人工智能",),
            city_labels=("杭州",),
            cohort_labels=("2027届",),
        ),
    )
    assert "project_id=77" in client.gets[0][0]
    assert "page_size=10" in client.gets[1][0]


def test_leihuo_adapter_uses_api_source_and_detail_probes():
    source_url = "https://leihuo.163.com/campus/#/full"
    target_url = "https://campus.163.com/app/detail/index?id=3738&projectId=77"
    client = _LeihuoClient()

    assert NETEASE_LEIHUO_ADAPTER.source_probe_url(source_url) == (
        "https://xiaozhao.leihuo.netease.com/api/apply/job/filter/show?project_id=77"
    )
    response = NETEASE_LEIHUO_ADAPTER.check_opportunity(
        source_url=source_url,
        target_url=target_url,
        config={},
        client=client,
    )

    assert response.status == 200
    assert client.gets == [
        (
            "https://xiaozhao.leihuo.netease.com/api/apply/job/detail/show"
            "?job_id=3738&project_id=77",
            {},
        )
    ]
