import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.brainco import BRAINCO_ADAPTER
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError


def _page(jobs):
    flight = (
        '6:[["$","$L1",null,{"initialJobs":'
        + json.dumps(jobs, ensure_ascii=False)
        + "}]]"
    )
    argument = json.dumps([1, flight], ensure_ascii=False)
    return SafeHttpResult(
        200,
        "https://www.brainco.cn/recruit/jobs",
        "强脑科技招聘",
        f"<html><script>self.__next_f.push({argument})</script></html>".encode(),
        False,
    )


class _Client:
    def __init__(self, jobs):
        self.jobs = jobs
        self.gets = []

    def get(self, url, **limits):
        self.gets.append((url, limits))
        return _page(self.jobs)


def test_brainco_adapter_collects_distinct_ssr_jobs():
    jobs = [
        {
            "id": "jobfull12345678",
            "documentId": "jobfull12345678",
            "title": "仿生关节算法工程师",
            "address": "深圳",
            "duties": "机器人控制算法",
            "claim": "本科及以上",
            "nature": "全职",
            "employmentType": "full-time",
        },
        {
            "id": "jobintern123456",
            "documentId": "jobintern123456",
            "title": "算法工程师",
            "address": "杭州、深圳",
            "duties": "面向2027届",
            "claim": "在校生",
            "nature": "实习",
            "employmentType": "internship",
        },
    ]
    client = _Client(jobs)

    result = BRAINCO_ADAPTER.collect(
        source_url="https://www.brainco.cn/recruit/jobs",
        config={},
        client=client,
        initial_response=SafeHttpResult(
            200, "https://www.brainco.cn/sitemap.xml", "", b"", False
        ),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.city_labels == ("深圳", "杭州")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="仿生关节算法工程师",
            target_url="https://www.brainco.cn/recruit/jobs#job-jobfull12345678",
            recruitment_type="SOCIAL",
            plan="全职招聘",
            location_text="深圳",
            category_labels=(),
            city_labels=("深圳",),
            cohort_labels=(),
        ),
        CollectedOpportunity(
            title="算法工程师",
            target_url="https://www.brainco.cn/recruit/jobs#job-jobintern123456",
            recruitment_type="INTERNSHIP",
            plan="实习招聘",
            location_text="杭州、深圳",
            category_labels=(),
            city_labels=("杭州", "深圳"),
            cohort_labels=("2027届",),
        ),
    )
    assert client.gets == [
        (
            "https://www.brainco.cn/recruit/jobs",
            {"max_response_bytes": 262_144},
        )
    ]


def test_brainco_adapter_rejects_a_missing_initial_jobs_payload():
    client = _Client([])
    client.get = lambda url, **limits: SafeHttpResult(
        200, url, "", b"<html></html>", False
    )
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_response_invalid.v1"
    ):
        BRAINCO_ADAPTER.collect(
            source_url="https://www.brainco.cn/recruit/jobs",
            config={},
            client=client,
            initial_response=SafeHttpResult(
                200, "https://www.brainco.cn", "", b"", False
            ),
            heartbeat=lambda: None,
        )


def test_brainco_adapter_rejects_another_source_path():
    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        BRAINCO_ADAPTER.source_probe_url("https://www.brainco.cn/recruit")
