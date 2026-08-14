import json

import pytest

from apps.opportunities.checks.adapters import CollectedOpportunity
from apps.opportunities.checks.dahua import DAHUA_ADAPTER
from apps.opportunities.checks.http import (
    MAX_ADAPTER_RESPONSE_BYTES,
    SafeHttpResult,
    SafeRequestError,
)


def _result(payload, *, url="https://job.dahuatech.com/talent-pool/api"):
    return SafeHttpResult(
        status=200,
        final_url=url,
        title="",
        body=json.dumps(payload, ensure_ascii=False).encode(),
        truncated=False,
    )


class _DahuaClient:
    def __init__(self):
        self.posts = []

    def post_json(self, url, payload, **limits):
        self.posts.append((url, payload, limits))
        category = "2" if payload["recruitType"] == 2 else "3"
        return _result(
            {
                "code": 200,
                "data": [
                    {
                        "jobAdId": "17a2d0e2-2301-4773-ba35-872924232356",
                        "jobAdName": "2027届测温算法工程师(J24396)",
                        "category": category,
                        "jobCategroyDescription": "算法类",
                        "workingPlace": "杭州市,国外",
                        "require": "面向27届毕业生。",
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("source_url", "recruit_type", "plan", "route"),
    (
        (
            "https://job.dahuatech.com/#/CampusPosition?id=11",
            "CAMPUS",
            "校园招聘",
            "CampusApply",
        ),
        (
            "https://job.dahuatech.com/#/SelfControl?id=16",
            "INTERNSHIP",
            "实习招聘",
            "AdvanceApply",
        ),
    ),
)
def test_dahua_adapter_collects_each_public_recruitment_list(
    source_url, recruit_type, plan, route
):
    client = _DahuaClient()

    result = DAHUA_ADAPTER.collect(
        source_url=source_url,
        config={},
        client=client,
        initial_response=SafeHttpResult(200, source_url, "大华招聘", b"", False),
        heartbeat=lambda: None,
    )

    assert result.complete is True
    assert result.pages_read == 1
    assert result.category_labels == ("算法类",)
    assert result.city_labels == ("杭州市", "国外")
    assert result.cohort_labels == ("2027届",)
    assert result.opportunities == (
        CollectedOpportunity(
            title="2027届测温算法工程师(J24396)",
            target_url=(
                "https://job.dahuatech.com/"
                f"#/{route}?id=17a2d0e2-2301-4773-ba35-872924232356"
            ),
            recruitment_type=recruit_type,
            plan=plan,
            location_text="杭州市、国外",
            category_labels=("算法类",),
            city_labels=("杭州市", "国外"),
            cohort_labels=("2027届",),
        ),
    )
    assert client.posts == [
        (
            "https://job.dahuatech.com/talent-pool/api/bs-info/list-position-by-search",
            {
                "companyCategory": "",
                "positionCategory": "",
                "workPlaceCode": "",
                "jobTitle": "",
                "recruitType": 2 if recruit_type == "CAMPUS" else 3,
            },
            {"max_response_bytes": MAX_ADAPTER_RESPONSE_BYTES},
        )
    ]


def test_dahua_adapter_rejects_an_unknown_source_route():
    source_url = "https://job.dahuatech.com/#/SocietyPosition?id=1"

    with pytest.raises(
        SafeRequestError, match="opportunities.adapter_config_invalid.v1"
    ):
        DAHUA_ADAPTER.collect(
            source_url=source_url,
            config={},
            client=_DahuaClient(),
            initial_response=SafeHttpResult(200, source_url, "大华招聘", b"", False),
            heartbeat=lambda: None,
        )
