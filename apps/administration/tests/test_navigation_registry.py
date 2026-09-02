from apps.administration.navigation_registry import ADMIN_NAVIGATION


def test_opportunities_are_a_dedicated_sixth_navigation_group() -> None:
    assert len(ADMIN_NAVIGATION) == 8
    assert ADMIN_NAVIGATION[5].label == "招聘管理"
    assert tuple(item.key for item in ADMIN_NAVIGATION[5].items) == (
        "opportunities-reviews",
        "opportunities-jobs",
        "opportunities-sources",
        "opportunities-runs",
        "opportunities-settings",
    )
    assert all(
        item.key != "opportunities"
        for index, group in enumerate(ADMIN_NAVIGATION)
        if index != 5
        for item in group.items
    )


def test_agents_are_the_dedicated_seventh_navigation_group() -> None:
    group = ADMIN_NAVIGATION[6]
    assert group.label == "AI 配置"
    assert tuple(item.key for item in group.items) == (
        "agent-endpoints",
        "agent-profiles",
    )


def test_learning_pages_remain_in_their_own_navigation_group() -> None:
    group = ADMIN_NAVIGATION[7]
    assert group.label == "智能与题库"
    assert tuple(item.key for item in group.items) == (
        "learning-documents",
        "question-banks",
        "question-bank-queue",
    )
