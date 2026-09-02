from types import SimpleNamespace
from uuid import uuid4

from apps.administration.presentation import context, opportunity_attention


def test_opportunity_attention_reads_only_visible_navigation_counts(
    monkeypatch,
) -> None:
    actor_id = uuid4()
    calls = []

    def review_count(*, actor_id):
        calls.append(("reviews", actor_id))
        return 37

    def unread_count(*, recipient_id, target_type):
        calls.append((target_type, recipient_id))
        return 4

    monkeypatch.setattr(opportunity_attention, "admin_open_review_count", review_count)
    monkeypatch.setattr(
        opportunity_attention,
        "unread_target_notification_count",
        unread_count,
    )

    assert opportunity_attention.opportunity_attention_counts(actor_id=actor_id) == (
        37,
        4,
    )
    assert calls == [
        ("reviews", actor_id),
        (opportunity_attention.OPPORTUNITY_CHECK_RUN_TARGET, actor_id),
    ]


def test_administration_shell_reuses_opportunity_counts(monkeypatch) -> None:
    actor_id = uuid4()
    captured_counts = {}

    monkeypatch.setattr(
        context,
        "opportunity_attention_counts",
        lambda **kwargs: (37, 4),
    )
    monkeypatch.setattr(
        context,
        "admin_article_appeal_review_count",
        lambda **kwargs: 2,
    )
    monkeypatch.setattr(
        context,
        "admin_report_review_count",
        lambda **kwargs: 3,
    )
    monkeypatch.setattr(
        context,
        "admin_pending_tag_review_count",
        lambda **kwargs: 5,
    )
    monkeypatch.setattr(
        context,
        "admin_learning_appeal_page",
        lambda **kwargs: SimpleNamespace(total_items=6),
    )

    def navigation(*, review_counts):
        captured_counts.update(review_counts)
        return ("navigation",)

    monkeypatch.setattr(context, "resolved_admin_navigation", navigation)
    request = SimpleNamespace(
        administration_authorized=True,
        account_id=actor_id,
        resolver_match=SimpleNamespace(view_name="admin:opportunities"),
    )

    result = context.administration_shell(request)

    assert captured_counts["opportunities"] == 41
    assert result["opportunity_admin_review_count"] == 37
    assert result["opportunity_admin_failure_count"] == 4
    assert result["admin_navigation_groups"] == ("navigation",)
