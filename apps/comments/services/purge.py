from django.db import transaction

from apps.comments.models import DiscussionThread
from apps.comments.targets import DiscussionTargetType
from apps.content.public import ArticleCommentPurgeResult
from apps.core.ids import normalize_ulid


def purge_article_comments(article_id: str) -> ArticleCommentPurgeResult:
    identity = normalize_ulid(article_id)
    with transaction.atomic():
        thread = (
            DiscussionThread.objects.select_for_update()
            .filter(
                target_type=DiscussionTargetType.ARTICLE,
                target_id=identity,
            )
            .first()
        )
        if thread is None:
            return ArticleCommentPurgeResult(comment_count=0)
        comment_count = thread.comments.count()
        thread.delete()
        return ArticleCommentPurgeResult(comment_count=comment_count)
