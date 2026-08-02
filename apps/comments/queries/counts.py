from collections.abc import Iterable

from django.db.models import Count
from django.utils import timezone

from apps.core.ids import normalize_ulid

from ..models import Comment, DiscussionThread


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ValueError("article id must be a ULID") from None


def article_comment_counts(*, article_ids: Iterable[str]) -> dict[str, int]:
    if isinstance(article_ids, (str, bytes)):
        raise ValueError("article ids must be a collection")
    try:
        identities = tuple(dict.fromkeys(_article_id(item) for item in article_ids))
    except TypeError:
        raise ValueError("article ids must be a collection") from None
    if not identities:
        return {}
    return {
        article_id: int(count)
        for article_id, count in (
            Comment.objects.filter(
                thread__target_type=DiscussionThread.TargetType.ARTICLE,
                thread__target_id__in=identities,
                state__in=(Comment.State.VISIBLE, Comment.State.DELETED),
                visible_at__lte=timezone.now(),
            )
            .values("thread__target_id")
            .annotate(comment_count=Count("id"))
            .values_list("thread__target_id", "comment_count")
        )
    }
