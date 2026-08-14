from apps.notifications.public import unread_target_notification_count
from apps.opportunities.public import admin_open_review_count

OPPORTUNITY_CHECK_RUN_TARGET = "opportunity_check_run"


def opportunity_attention_counts(*, actor_id) -> tuple[int, int]:
    review_count = admin_open_review_count(actor_id=actor_id)
    unread_run_count = unread_target_notification_count(
        recipient_id=actor_id,
        target_type=OPPORTUNITY_CHECK_RUN_TARGET,
    )
    return review_count, unread_run_count


__all__ = ["OPPORTUNITY_CHECK_RUN_TARGET", "opportunity_attention_counts"]
