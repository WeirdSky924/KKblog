from datetime import UTC, datetime
from types import SimpleNamespace

from apps.opportunities.checks.adapters import AdapterResult, CollectedOpportunity
from apps.opportunities.models import Opportunity
from apps.opportunities.services.collection import validate_adapter_result


def _candidate(title, cohorts, *, category, city):
    return CollectedOpportunity(
        title=title,
        target_url=f"https://jobs.example.com/{title}",
        recruitment_type=Opportunity.RecruitmentType.CAMPUS,
        plan="校园招聘",
        location_text=city,
        category_labels=(category,),
        city_labels=(city,),
        cohort_labels=cohorts,
    )


def _result(*opportunities):
    return AdapterResult(
        complete=True,
        opportunities=opportunities,
        category_labels=tuple(
            label for item in opportunities for label in item.category_labels
        ),
        city_labels=tuple(
            label for item in opportunities for label in item.city_labels
        ),
        cohort_labels=tuple(
            label for item in opportunities for label in item.cohort_labels
        ),
    )


def _validate(result, observed_at):
    return validate_adapter_result(
        result,
        source=SimpleNamespace(max_pages=50, max_opportunities=5000),
        allowed_hosts=frozenset({"jobs.example.com"}),
        observed_at=observed_at,
    )


def test_collection_keeps_only_current_and_next_recruitment_cohorts():
    result = _result(
        _candidate("old", ("2026届",), category="旧类别", city="旧城市"),
        _candidate("current", ("2027届",), category="当前类别", city="杭州"),
        _candidate("next", ("2028届",), category="下一届类别", city="上海"),
        _candidate("future", ("2029届",), category="未来类别", city="未来城市"),
        _candidate("unknown", (), category="未知类别", city="未知城市"),
        _candidate(
            "mixed",
            ("2026届", "2027届"),
            category="混合类别",
            city="北京",
        ),
    )

    validated = _validate(result, datetime(2026, 8, 14, tzinfo=UTC))

    assert [item.title for item in validated.opportunities] == [
        "current",
        "next",
        "unknown",
        "mixed",
    ]
    assert validated.opportunities[-1].cohort_labels == ("2027届",)
    assert set(validated.category_labels) == {
        "当前类别",
        "下一届类别",
        "未知类别",
        "混合类别",
    }
    assert set(validated.city_labels) == {"杭州", "上海", "未知城市", "北京"}
    assert validated.cohort_labels == ("2027届", "2028届")


def test_collection_cohort_window_rolls_over_each_july():
    result = _result(
        _candidate("2027", ("2027届",), category="研发", city="杭州"),
        _candidate("2028", ("2028届",), category="研发", city="杭州"),
        _candidate("2029", ("2029届",), category="研发", city="杭州"),
    )

    before_rollover = _validate(result, datetime(2027, 6, 30, tzinfo=UTC))
    after_rollover = _validate(result, datetime(2027, 7, 1, tzinfo=UTC))

    assert [item.title for item in before_rollover.opportunities] == ["2027", "2028"]
    assert [item.title for item in after_rollover.opportunities] == ["2028", "2029"]
