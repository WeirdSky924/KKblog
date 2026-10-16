from .errors import CommentPostingError


def normalize_comment_body(value: str) -> str:
    if not isinstance(value, str):
        raise CommentPostingError(
            "comments.body_invalid.v1",
            "评论正文需为 1 至 100 个字符。",
            field="body",
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 1 <= len(normalized) <= 100 or any(
        not char.isprintable() and char not in "\n\t" for char in normalized
    ):
        raise CommentPostingError(
            "comments.body_invalid.v1",
            "评论正文需为 1 至 100 个字符。",
            field="body",
        )
    return normalized


def normalize_guestbook_body(value: str) -> str:
    if not isinstance(value, str):
        raise CommentPostingError(
            "comments.guestbook_body_invalid.v1",
            "留言需为 1 至 100 个字符，中文最多 50 字，且不能包含换行。",
            field="body",
        )
    normalized = value.strip()
    cjk_count = sum("\u3400" <= char <= "\u9fff" for char in normalized)
    if (
        not 1 <= len(normalized) <= 100
        or cjk_count > 50
        or any(not char.isprintable() for char in normalized)
    ):
        raise CommentPostingError(
            "comments.guestbook_body_invalid.v1",
            "留言需为 1 至 100 个字符，中文最多 50 字，且不能包含换行。",
            field="body",
        )
    return normalized
