from collections.abc import Callable

ArticleReaderMask = Callable[[str], bool]


def _unmasked(_article_id: str) -> bool:
    return False


_reader_mask: ArticleReaderMask = _unmasked


def register_article_reader_mask(mask: ArticleReaderMask) -> None:
    global _reader_mask
    if not callable(mask):
        raise TypeError("article reader mask must be callable")
    _reader_mask = mask


def article_is_reader_masked(article_id: str) -> bool:
    result = _reader_mask(article_id)
    if type(result) is not bool:
        raise TypeError("article reader mask must return a boolean")
    return result
