from apps.administration.navigation_registry import resolved_admin_navigation
from apps.administration.presentation.opportunity_attention import (
    opportunity_attention_counts,
)
from apps.content.public import admin_pending_tag_review_count
from apps.learning.public import admin_learning_appeal_page
from apps.moderation.public import (
    admin_article_appeal_review_count,
    admin_report_review_count,
)


def administration_shell(request):
    if not getattr(request, "administration_authorized", False):
        return {}
    match = getattr(request, "resolver_match", None)
    actor_id = request.account_id
    review_counts = {
        "articles": admin_article_appeal_review_count(actor_id=actor_id),
        "reports": admin_report_review_count(actor_id=actor_id),
        "tags": admin_pending_tag_review_count(actor_id=actor_id),
    }
    opportunity_reviews, opportunity_failures = opportunity_attention_counts(
        actor_id=actor_id
    )
    review_counts["opportunities"] = opportunity_reviews + opportunity_failures
    review_counts["learning-documents"] = admin_learning_appeal_page(
        actor_id=actor_id,
        state="PENDING",
        page=1,
        page_size=20,
    ).total_items
    return {
        "admin_navigation_groups": resolved_admin_navigation(
            review_counts=review_counts
        ),
        "admin_current_route": getattr(match, "view_name", ""),
        "opportunity_admin_review_count": opportunity_reviews,
        "opportunity_admin_failure_count": opportunity_failures,
    }
