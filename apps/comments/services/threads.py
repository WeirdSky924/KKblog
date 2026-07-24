from django.db import transaction

from apps.content.public import ArticleCommentTarget, article_comment_target

from ..models import DiscussionThread
from ..targets import DiscussionTargetType


def sync_article_thread(
    *, actor_id, article_id: str
) -> tuple[DiscussionThread, ArticleCommentTarget]:
    target = article_comment_target(actor_id=actor_id, article_id=article_id)
    defaults = {
        "owner_id": target.owner_id,
        "comments_enabled": target.comments_enabled,
        "view_login_required": target.view_login_required,
        "post_login_required": target.post_login_required,
    }
    with transaction.atomic():
        thread, _ = DiscussionThread.objects.update_or_create(
            target_type=DiscussionTargetType.ARTICLE,
            target_id=target.article_id,
            defaults=defaults,
        )
    return thread, target
