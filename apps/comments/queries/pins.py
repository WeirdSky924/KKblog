from uuid import UUID

from django.db import ProgrammingError

from ..models import CommentPin


def _is_missing_table(error: ProgrammingError) -> bool:
    return getattr(error.__cause__, "sqlstate", None) == "42P01"


def pinned_comment_id(*, thread_id: UUID | str) -> str | None:
    try:
        return (
            CommentPin.objects.filter(thread_id=thread_id)
            .values_list("comment_id", flat=True)
            .first()
        )
    except ProgrammingError as exc:
        if _is_missing_table(exc):
            return None
        raise
