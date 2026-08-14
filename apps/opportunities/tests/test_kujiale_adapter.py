import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.kujiale import KUJIALE_ADAPTER


def _result(
    payload, *, url="https://ehr-headcount.qunhequnhe.com/api/v1/moka/job/search"
):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _KujialeClient:
    def __init__(self):
        self.gets = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        return _result(
            {
                "c": "0",
                "m": "",
                "d": {
                    "total": 3,
                    "jobs": [
                        {
                            "jobId": "algorithm-job",
                            "title": "科研算法实习生",
                            "commitment": "实习",
                            "locations": [
                                {
                                    "province": "浙江",
                                    "city": "杭州市",
                                    "address": "余杭塘路",
                                }
                            ],
                            "functions": [{"id": 4004, "name": "技术"}],
                        },
                        {
                            "jobId": "backend-job",
                            "title": "后端开发工程师-27届校招",
                            "commitment": "全职",
                            "locations": [
                                {
                                    "province": "浙江",
                                    "city": "杭州市",
                                    "address": "余杭塘路",
                                }
                            ],
                            "functions": [{"id": 4004, "name": "技术"}],
                        },
                        {
                            "jobId": "product-job",
                            "title": "AI产品经理-27届校招",
                            "commitment": "全职",
                            "locations": [],
                            "functions": [{"id": 4005, "name": "产品"}],
                        },
                    ],
                },
            },
            url=url,
        )


def _collect(source_url):
    client = _KujialeClient()
    result = KUJIALE_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "酷家乐校园招聘", b"", False),
        heartbeat=lambda: None,
    )
    return result, client


def test_kujiale_algorithm_source_collects_only_algorithm_technical_jobs():
    result, client = _collect(
        "https://www.kujiale.com/pub/hr-recruit/campus/postlist?post=72628"
    )

    assert result.complete is True
    assert result.category_labels == ("技术",)
    assert result.city_labels == ("杭州市",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="科研算法实习生",
            target_url=(
                "https://www.kujiale.com/pub/hr-recruit/campus/postdetail/algorithm-job"
            ),
            recruitment_type="INTERNSHIP",
            plan="实习招聘",
            location_text="浙江·杭州市",
            category_labels=("技术",),
            city_labels=("杭州市",),
            cohort_labels=(),
        ),
    )
    assert client.gets == [
        (
            "https://ehr-headcount.qunhequnhe.com/api/v1/moka/job/search?"
            "limit=100&offset=0&mode=campus",
            {"max_response_bytes": 262_144},
        )
    ]


def test_kujiale_development_source_excludes_algorithm_jobs():
    result, _client = _collect(
        "https://www.kujiale.com/pub/hr-recruit/campus/postlist?post=66890"
    )

    assert result.opportunities == (
        CollectedOpportunity(
            title="后端开发工程师-27届校招",
            target_url=(
                "https://www.kujiale.com/pub/hr-recruit/campus/postdetail/backend-job"
            ),
            recruitment_type="CAMPUS",
            plan="校园招聘",
            location_text="浙江·杭州市",
            category_labels=("技术",),
            city_labels=("杭州市",),
            cohort_labels=("2027届",),
        ),
    )


def test_kujiale_adapter_rejects_unknown_legacy_category_anchor():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        _collect("https://www.kujiale.com/pub/hr-recruit/campus/postlist?post=1")
