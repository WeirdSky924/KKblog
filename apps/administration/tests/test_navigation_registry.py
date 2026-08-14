from apps.administration.navigation_registry import ADMIN_NAVIGATION


def test_opportunities_are_a_dedicated_sixth_navigation_group() -> None:
    assert len(ADMIN_NAVIGATION) == 6
    assert ADMIN_NAVIGATION[-1].label == "招聘管理"
    assert tuple(item.key for item in ADMIN_NAVIGATION[-1].items) == ("opportunities",)
    assert all(
        item.key != "opportunities"
        for group in ADMIN_NAVIGATION[:-1]
        for item in group.items
    )
