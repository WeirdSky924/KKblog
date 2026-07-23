from collections.abc import Callable
from uuid import UUID

from django.db.models import QuerySet

from ..models import AuthorContentMask

ArticleReaderMask = Callable[[str], bool]
ArticleReaderScope = Callable[[QuerySet], QuerySet]


def _unmasked(_article_id: str) -> bool:
    return False


_reader_mask: ArticleReaderMask = _unmasked


def _unfiltered(queryset: QuerySet) -> QuerySet:
    return queryset


_reader_scope: ArticleReaderScope = _unfiltered


def register_article_reader_mask(mask: ArticleReaderMask) -> None:
    global _reader_mask
    if not callable(mask):
        raise TypeError("article reader mask must be callable")
    _reader_mask = mask


def register_article_reader_scope(scope: ArticleReaderScope) -> None:
    global _reader_scope
    if not callable(scope):
        raise TypeError("article reader scope must be callable")
    _reader_scope = scope


def article_is_reader_masked(article_id: str) -> bool:
    result = _reader_mask(article_id)
    if type(result) is not bool:
        raise TypeError("article reader mask must return a boolean")
    return result


def apply_article_reader_scope(queryset: QuerySet) -> QuerySet:
    scoped = _reader_scope(queryset)
    if not isinstance(scoped, QuerySet) or scoped.model is not queryset.model:
        raise TypeError("article reader scope must return the same model queryset")
    return scoped


def author_is_content_masked(author_id) -> bool:
    try:
        identity = UUID(str(author_id))
    except (TypeError, ValueError):
        return True
    return AuthorContentMask.objects.filter(author_id=identity, masked=True).exists()
