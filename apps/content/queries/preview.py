from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from apps.media.public import (
    RenderingError,
    markdown_media_ids,
    render_markdown,
    render_tiptap,
    tiptap_media_ids,
)

from ..snapshots import ArticleBodyLimit, ContentFormat
from .discovery import sanitized_article_plain_text


class ArticlePreviewError(ValueError):
    def __init__(self, message: str = "正文格式不合法，无法生成预览。") -> None:
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AuthorArticlePreview:
    html: str
    sanitizer_version: str
    serialized_body: str
    body_bytes: int
    text_character_count: int
    media_count: int


def _media_ids(values) -> tuple[str, ...]:
    if values is None:
        return ()
    try:
        normalized = tuple(str(value) for value in values)
    except TypeError:
        raise ArticlePreviewError("正文图片信息不合法。") from None
    if len(normalized) > 1000 or len(set(normalized)) != len(normalized):
        raise ArticlePreviewError("正文图片信息不合法。")
    return normalized


def preview_article_body(
    *,
    content_format: ContentFormat | str,
    body: str | dict[str, Any],
    body_asset_ids=None,
    body_limit: ArticleBodyLimit | None = None,
) -> AuthorArticlePreview:
    try:
        normalized_format = ContentFormat(content_format)
    except (TypeError, ValueError):
        raise ArticlePreviewError from None
    try:
        if normalized_format == ContentFormat.MARKDOWN:
            if not isinstance(body, str):
                raise RenderingError("Markdown source must be text")
            serialized = body
        else:
            if not isinstance(body, dict):
                raise RenderingError("TipTap source must be an object")
            serialized = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        maximum = (body_limit or ArticleBodyLimit.configured()).maximum_bytes
        body_bytes = len(serialized.encode("utf-8"))
        if body_bytes > maximum:
            raise ArticlePreviewError(f"正文不能超过 {maximum} 字节。")
        if normalized_format == ContentFormat.MARKDOWN:
            referenced = markdown_media_ids(body)
        else:
            referenced = tiptap_media_ids(body)
        submitted = _media_ids(body_asset_ids)
        allowed = submitted or referenced
        if submitted and set(submitted) != set(referenced):
            raise ArticlePreviewError("正文图片引用与提交列表不一致。")
        rendered = (
            render_markdown(body, allowed_media_ids=allowed)
            if normalized_format == ContentFormat.MARKDOWN
            else render_tiptap(body, allowed_media_ids=allowed)
        )
    except ArticlePreviewError:
        raise
    except (RenderingError, TypeError, ValueError, RecursionError):
        raise ArticlePreviewError from None
    text = sanitized_article_plain_text(rendered.html)
    return AuthorArticlePreview(
        html=rendered.html,
        sanitizer_version=rendered.sanitizer_version,
        serialized_body=serialized,
        body_bytes=body_bytes,
        text_character_count=len(text),
        media_count=len(referenced),
    )
