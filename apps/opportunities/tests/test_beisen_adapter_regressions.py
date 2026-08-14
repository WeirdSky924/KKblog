from apps.opportunities.checks.beisen import _cohorts


def test_beisen_cohorts_accept_short_labels_and_graduation_year_text():
    assert _cohorts(
        "【27届】AI实习生",
        "国内毕业时间2027年1月-12月；海外毕业时间2026年9月-2027年9月。",
    ) == ("2027届", "2026届")
