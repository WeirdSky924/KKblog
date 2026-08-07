from collections.abc import Iterable

from django.db import ProgrammingError
from django.db.models import Count

from apps.core.ids import normalize_ulid

from ..models import ArticleLike


def _is_missing_table(error: ProgrammingError) -> bool:
    return getattr(error.__cause__, "sqlstate", None) == "42P01"


def article_like_counts(*, article_ids: Iterable[str]) -> dict[str, int]:
    normalized = tuple(dict.fromkeys(normalize_ulid(value) for value in article_ids))
    if not normalized:
        return {}
    try:
        rows = (
            ArticleLike.objects.filter(article_id__in=normalized)
            .values("article_id")
            .annotate(total=Count("id"))
        )
        return {row["article_id"]: row["total"] for row in rows}
    except ProgrammingError as exc:
        if _is_missing_table(exc):
            return {}
        raise


def article_like_count(*, article_id: str) -> int:
    normalized = normalize_ulid(article_id)
    return article_like_counts(article_ids=(normalized,)).get(normalized, 0)
