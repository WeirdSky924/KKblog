from collections.abc import Callable
from dataclasses import dataclass

from django.apps import apps as django_apps


@dataclass(frozen=True, slots=True)
class ArticleCommentPurgeResult:
    comment_count: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.comment_count, bool)
            or not isinstance(self.comment_count, int)
            or self.comment_count < 0
        ):
            raise ValueError("comment_count must be a non-negative integer")


ArticleCommentPurge = Callable[[str], ArticleCommentPurgeResult]
_comment_purge_port: ArticleCommentPurge | None = None


class ArticleCommentPurgeUnavailable(RuntimeError):
    error_code = "content.comment_purge_unavailable.v1"


def register_article_comment_purge(
    port: ArticleCommentPurge,
    *,
    replace: bool = False,
) -> None:
    """Register the comments-owner transaction participant for article purge."""
    global _comment_purge_port
    if not callable(port):
        raise TypeError("article comment purge port must be callable")
    if _comment_purge_port is not None and not replace:
        raise ValueError("article comment purge port is already registered")
    _comment_purge_port = port


def purge_article_comments(article_id: str) -> ArticleCommentPurgeResult:
    if _comment_purge_port is None:
        if django_apps.is_installed("apps.comments"):
            raise ArticleCommentPurgeUnavailable
        return ArticleCommentPurgeResult(comment_count=0)
    result = _comment_purge_port(article_id)
    if not isinstance(result, ArticleCommentPurgeResult):
        raise TypeError("article comment purge port returned an invalid result")
    return result
