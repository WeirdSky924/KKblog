from django.db import IntegrityError, connection, transaction

from apps.core.ids import normalize_ulid


class ViewCounterError(LookupError):
    code = "discovery.article_not_found.v1"

    def __init__(self) -> None:
        super().__init__("未找到请求的文章。")


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ViewCounterError from None


def record_article_view(*, article_id: str) -> int:
    identity = _article_id(article_id)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO discovery_article_view_counter
                        (article_id, count, updated_at)
                    VALUES (%s, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (article_id) DO UPDATE
                    SET count = discovery_article_view_counter.count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING count
                    """,
                    [identity],
                )
                row = cursor.fetchone()
    except IntegrityError:
        raise ViewCounterError from None
    if row is None:
        raise ViewCounterError
    return int(row[0])
