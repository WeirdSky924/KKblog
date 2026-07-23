from collections.abc import Iterable

from apps.core.ids import normalize_ulid

from ..models import ArticleViewCounter


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ValueError("article id must be a ULID") from None


def article_view_count(*, article_id: str) -> int:
    identity = _article_id(article_id)
    count = (
        ArticleViewCounter.objects.filter(article_id=identity)
        .values_list("count", flat=True)
        .first()
    )
    return int(count or 0)


def article_view_counts(*, article_ids: Iterable[str]) -> dict[str, int]:
    if isinstance(article_ids, (str, bytes)):
        raise ValueError("article ids must be a collection")
    try:
        identities = tuple(dict.fromkeys(_article_id(item) for item in article_ids))
    except TypeError:
        raise ValueError("article ids must be a collection") from None
    return {
        article_id: int(count)
        for article_id, count in ArticleViewCounter.objects.filter(
            article_id__in=identities
        ).values_list("article_id", "count")
    }
