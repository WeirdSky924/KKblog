from dataclasses import dataclass

import pytest

from apps.opportunities.checks.alibaba import AlibabaCampusAdapter
from apps.opportunities.checks.bytedance import ByteDanceCampusAdapter
from apps.opportunities.checks.hikvision import HikvisionAdapter
from apps.opportunities.checks.http import SafeHttpResult, SafeRequestError
from apps.opportunities.checks.xiaomi import XiaomiAdapter


@dataclass
class _Collector:
    result: dict

    def collect(self, **kwargs):
        self.request = kwargs
        return self.result


def _result(collector: str, *, recruitment_type="CAMPUS") -> dict:
    return {
        "version": 1,
        "collector": collector,
        "complete": True,
        "pages_read": 2,
        "opportunities": [
            {
                "title": "算法工程师",
                "target_url": "https://jobs.example.com/position/1",
                "recruitment_type": recruitment_type,
                "plan": "2027 届校园招聘",
                "location_text": "杭州、上海",
                "category_labels": ["算法"],
                "city_labels": ["杭州", "上海"],
                "cohort_labels": ["2027届"],
            }
        ],
        "category_labels": ["算法"],
        "city_labels": ["杭州", "上海"],
        "cohort_labels": ["2027届"],
    }


@pytest.mark.parametrize(
    ("adapter", "source_url", "collector_key", "host", "recruitment_type"),
    (
        (
            HikvisionAdapter,
            "https://campushr.hikvision.com/school?schoolType=nozxf",
            "hikvision-v1",
            "campushr.hikvision.com",
            "CAMPUS",
        ),
        (
            ByteDanceCampusAdapter,
            "https://jobs.bytedance.com/campus/position",
            "bytedance-campus-v1",
            "jobs.bytedance.com",
            "CAMPUS",
        ),
        (
            AlibabaCampusAdapter,
            "https://campus-talent.alibaba.com/campus/position?batchId=100000760001",
            "alibaba-campus-v1",
            "campus-talent.alibaba.com",
            "CAMPUS",
        ),
    ),
)
def test_browser_source_adapter_converts_bounded_public_rows(
    adapter, source_url, collector_key, host, recruitment_type
) -> None:
    raw = _result(collector_key, recruitment_type=recruitment_type)
    raw["opportunities"][0]["target_url"] = f"https://{host}/position/1"
    collector = _Collector(raw)

    result = adapter(collector=collector).collect(
        source_url=source_url,
        config={
            "_max_pages": 10,
            "_max_opportunities": 500,
            "_max_duration_seconds": 90,
        },
        client=object(),
        initial_response=SafeHttpResult(200, source_url, "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 2
    assert result.opportunities[0].title == "算法工程师"
    assert result.opportunities[0].city_labels == ("杭州", "上海")
    assert collector.request["adapter_key"] == collector_key
    assert collector.request["allowed_hosts"] == frozenset({host})
    assert collector.request["timeout_seconds"] == 90


@pytest.mark.parametrize(
    ("source_url", "collector_key", "website_path", "recruitment_type"),
    (
        (
            "https://xiaomi.jobs.f.mioffice.cn/campus/?spread=J7NS6YR",
            "xiaomi-campus-v1",
            "campus",
            "CAMPUS",
        ),
        (
            "https://xiaomi.jobs.f.mioffice.cn/internship/?spread=6AA3R7B",
            "xiaomi-intern-v1",
            "internship",
            "INTERNSHIP",
        ),
    ),
)
def test_xiaomi_adapters_keep_campus_and_internship_sources_separate(
    source_url, collector_key, website_path, recruitment_type
) -> None:
    raw = _result(collector_key, recruitment_type=recruitment_type)
    raw["opportunities"][0]["target_url"] = (
        f"https://xiaomi.jobs.f.mioffice.cn/{website_path}/position/1/detail"
    )
    collector = _Collector(raw)

    result = XiaomiAdapter(
        collector_key=collector_key,
        website_path=website_path,
        recruitment_type=recruitment_type,
        collector=collector,
    ).collect(
        source_url=source_url,
        config={"_max_pages": 10, "_max_opportunities": 500},
        client=object(),
        initial_response=SafeHttpResult(200, source_url, "", b"", False),
        heartbeat=lambda: None,
    )

    assert result.opportunities[0].recruitment_type == recruitment_type


def test_browser_source_adapter_rejects_cross_source_url() -> None:
    adapter = HikvisionAdapter(collector=_Collector(_result("hikvision-v1")))

    with pytest.raises(SafeRequestError) as error:
        adapter.collect(
            source_url="https://jobs.example.com/school",
            config={},
            client=object(),
            initial_response=SafeHttpResult(
                200, "https://jobs.example.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )

    assert error.value.error_code == "opportunities.adapter_config_invalid.v1"


def test_browser_source_adapter_rejects_invalid_public_row() -> None:
    raw = _result("hikvision-v1")
    raw["opportunities"][0]["title"] = ""
    adapter = HikvisionAdapter(collector=_Collector(raw))

    with pytest.raises(SafeRequestError) as error:
        adapter.collect(
            source_url="https://campushr.hikvision.com/school?schoolType=nozxf",
            config={},
            client=object(),
            initial_response=SafeHttpResult(
                200, "https://campushr.hikvision.com", "", b"", False
            ),
            heartbeat=lambda: None,
        )

    assert error.value.error_code == "opportunities.adapter_response_invalid.v1"
