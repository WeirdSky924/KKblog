from dataclasses import dataclass

import pytest

from apps.opportunities.checks.feishu import FEISHU_ADAPTER
from apps.opportunities.checks.http import SafeRequestError


@dataclass
class _Collector:
    result: dict

    def collect(self, **kwargs):
        self.request = kwargs
        return self.result


def _result():
    return {
        "version": 1,
        "collector": "feishu-career-v1",
        "complete": True,
        "pages_read": 2,
        "opportunities": [
            {
                "title": "后端开发工程师",
                "target_url": (
                    "https://fastbase.jobs.feishu.cn/588906/position/123456789/detail"
                ),
                "recruitment_type": "CAMPUS",
                "plan": "2027 届校园招聘",
                "location_text": "深圳",
                "category_labels": ["研发"],
                "city_labels": ["深圳"],
                "cohort_labels": ["2027届"],
                "published_at": 1787915400000,
            }
        ],
        "category_labels": ["研发"],
        "city_labels": ["深圳"],
        "cohort_labels": ["2027届"],
    }


def test_feishu_adapter_uses_source_host_only_for_browser_request():
    collector = _Collector(_result())
    source = "https://fastbase.jobs.feishu.cn/588906/position/list"
    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 10,
            "_max_opportunities": 100,
            "_max_duration_seconds": 60,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.opportunities[0].cohort_labels == ("2027届",)
    assert collector.request["allowed_hosts"] == ("fastbase.jobs.feishu.cn",)
    assert collector.request["adapter_key"] == "feishu-career-v1"


def test_feishu_adapter_accepts_the_verified_global_intco_tenant():
    collector = _Collector(_result())
    source = "https://global-intco.jobs.feishu.cn/840753/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("global-intco.jobs.feishu.cn",)


def test_feishu_adapter_accepts_the_verified_yuanqi_tenant():
    collector = _Collector(_result())
    source = "https://k11pnjpvz1.jobs.feishu.cn/index"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("k11pnjpvz1.jobs.feishu.cn",)


def test_feishu_adapter_accepts_nested_position_list_for_verified_tars_tenant():
    collector = _Collector(_result())
    source = "https://tarsrobot.jobs.feishu.cn/index/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("tarsrobot.jobs.feishu.cn",)


def test_feishu_adapter_accepts_prefixed_position_list_for_verified_smartlogic_tenant():
    collector = _Collector(_result())
    source = "https://smartlogictech.jobs.feishu.cn/xiaozhao/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("smartlogictech.jobs.feishu.cn",)


def test_feishu_adapter_accepts_nested_position_list_for_verified_dexmal_tenant():
    collector = _Collector(_result())
    source = "https://dexmal-inc.jobs.feishu.cn/index/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("dexmal-inc.jobs.feishu.cn",)


def test_feishu_adapter_accepts_nested_position_list_for_verified_sentury_tenant():
    collector = _Collector(_result())
    source = "https://senturytire.jobs.feishu.cn/029966/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("senturytire.jobs.feishu.cn",)


def test_feishu_adapter_accepts_prefixed_position_list_for_verified_xpeng_tenant():
    collector = _Collector(_result())
    source = "https://xiaopeng.jobs.feishu.cn/campus/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("xiaopeng.jobs.feishu.cn",)


def test_feishu_adapter_accepts_nested_position_list_for_verified_qunar_tenant():
    collector = _Collector(_result())
    source = "https://hf7l9aiqzx.jobs.feishu.cn/index/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("hf7l9aiqzx.jobs.feishu.cn",)


def test_feishu_adapter_accepts_nested_position_list_for_verified_radrock_tenant():
    collector = _Collector(_result())
    source = "https://radrocktech.jobs.feishu.cn/index/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("radrocktech.jobs.feishu.cn",)


@pytest.mark.parametrize(
    "source",
    (
        "https://weikezhijia.jobs.feishu.cn/MSXF/position/list",
        "https://weikezhijia.jobs.feishu.cn/MSXF0619/position/list",
    ),
)
def test_feishu_adapter_accepts_verified_weikezhijia_lists(source):
    collector = _Collector(_result())

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("weikezhijia.jobs.feishu.cn",)


def test_feishu_adapter_accepts_verified_fanuc_social_list():
    collector = _Collector(_result())
    source = "https://iwhih7is28.jobs.feishu.cn/index"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("iwhih7is28.jobs.feishu.cn",)


def test_feishu_adapter_accepts_verified_leiniao_social_list():
    collector = _Collector(_result())
    source = "https://leiniao-ibg.jobs.feishu.cn/index"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("leiniao-ibg.jobs.feishu.cn",)


def test_feishu_adapter_accepts_verified_anker_list():
    collector = _Collector(_result())
    source = "https://anker-in.jobs.feishu.cn/campushirecn/position/list"

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("anker-in.jobs.feishu.cn",)


@pytest.mark.parametrize(
    "source",
    (
        "https://kwh0jtf778.jobs.feishu.cn/229043/position/list",
        "https://kwh0jtf778.jobs.feishu.cn/index/position/list",
    ),
)
def test_feishu_adapter_accepts_verified_hesai_lists(source):
    collector = _Collector(_result())

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("kwh0jtf778.jobs.feishu.cn",)


@pytest.mark.parametrize(
    "source",
    (
        "https://leoglobal.jobs.feishu.cn/leosz/position/list",
        "https://leoglobal.jobs.feishu.cn/leoxz/position/list",
    ),
)
def test_feishu_adapter_accepts_verified_leoglobal_lists(source):
    collector = _Collector(_result())

    result = FEISHU_ADAPTER.__class__(collector=collector).collect(
        source_url=source,
        config={
            "_max_pages": 100,
            "_max_opportunities": 5000,
            "_max_duration_seconds": 600,
        },
        client=object(),
        initial_response=None,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert collector.request["allowed_hosts"] == ("leoglobal.jobs.feishu.cn",)


@pytest.mark.parametrize(
    "source",
    (
        "http://fastbase.jobs.feishu.cn/588906/position/list",
        "https://fastbase.jobs.feishu.cn/588906/login",
        "https://unknown.jobs.feishu.cn/position/list",
    ),
)
def test_feishu_adapter_rejects_non_public_list_source(source):
    with pytest.raises(SafeRequestError) as error:
        FEISHU_ADAPTER.collect(
            source_url=source,
            config={},
            client=object(),
            initial_response=None,
            heartbeat=lambda: None,
        )
    assert error.value.error_code == "opportunities.adapter_config_invalid.v1"


def test_feishu_adapter_rejects_malformed_collector_rows():
    raw = _result()
    raw["opportunities"][0]["title"] = ""
    collector = _Collector(raw)
    with pytest.raises(SafeRequestError) as error:
        FEISHU_ADAPTER.__class__(collector=collector).collect(
            source_url="https://fastbase.jobs.feishu.cn/588906/position/list",
            config={},
            client=object(),
            initial_response=None,
            heartbeat=lambda: None,
        )
    assert error.value.error_code == "opportunities.adapter_response_invalid.v1"
