from apps.administration.navigation_registry import resolved_admin_navigation
from apps.content.public import admin_pending_tag_review_count
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
    return {
        "admin_navigation_groups": resolved_admin_navigation(
            review_counts=review_counts
        ),
        "admin_current_route": getattr(match, "view_name", ""),
    }
