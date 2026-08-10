from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.media.public import (
    CURRENT_TIPTAP_SCHEMA_VERSION,
    RenderingError,
    TipTapAttachmentMetadata,
    markdown_media_ids,
)

from ..rendering import (
    ArticleRenderingMode,
    normalize_article_tiptap_body,
    render_article_body,
)
from ..rendering_policy import (
    content_error_for_rendering,
)
from ..snapshots import ArticleBodyLimit, ContentFormat


class ArticlePreviewError(ValueError):
    def __init__(
        self,
        message: str = "正文格式不合法，无法生成预览。",
        *,
        code: str = "content.body_invalid.v1",
    ) -> None:
        self.code = code
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
    block_start_lines: tuple[int, ...]


def _media_ids(values) -> tuple[str, ...]:
    if values is None:
        return ()
    try:
        normalized = tuple(str(value) for value in values)
    except TypeError:
        raise ArticlePreviewError(
            "正文图片信息不合法。", code="content.media_invalid.v1"
        ) from None
    if len(normalized) > 1000 or len(set(normalized)) != len(normalized):
        raise ArticlePreviewError(
            "正文图片信息不合法。", code="content.media_invalid.v1"
        )
    return normalized


def preview_article_body(
    *,
    content_format: ContentFormat | str,
    body: str | dict[str, Any],
    body_asset_ids=None,
    body_limit: ArticleBodyLimit | None = None,
    tiptap_schema_version: int | None = None,
    attachment_asset_id: str | None = None,
    attachment_metadata: TipTapAttachmentMetadata | None = None,
    mode: ArticleRenderingMode | str = ArticleRenderingMode.STRICT,
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
            normalized_tiptap = normalize_article_tiptap_body(
                body,
                schema_version=(
                    tiptap_schema_version
                    if tiptap_schema_version is not None
                    else CURRENT_TIPTAP_SCHEMA_VERSION
                ),
            )
            serialized = normalized_tiptap.serialized
        maximum = (body_limit or ArticleBodyLimit.configured()).maximum_bytes
        body_bytes = len(serialized.encode("utf-8"))
        if body_bytes > maximum:
            raise ArticlePreviewError(
                f"正文不能超过 {maximum} 字节。",
                code="content.body_too_large.v1",
            )
        if normalized_format == ContentFormat.MARKDOWN:
            referenced = markdown_media_ids(body)
        else:
            referenced = normalized_tiptap.body_media_ids
        submitted = _media_ids(body_asset_ids)
        allowed = submitted or referenced
        if submitted and set(submitted) != set(referenced):
            raise ArticlePreviewError(
                "正文图片引用与提交列表不一致。",
                code="content.media_invalid.v1",
            )
        rendered = render_article_body(
            content_format=normalized_format,
            body=(
                normalized_tiptap
                if normalized_format == ContentFormat.TIPTAP_JSON
                else body
            ),
            tiptap_schema_version=(
                normalized_tiptap.schema_version
                if normalized_format == ContentFormat.TIPTAP_JSON
                else None
            ),
            allowed_media_ids=allowed,
            allowed_attachment_id=attachment_asset_id or None,
            attachment_metadata=attachment_metadata,
            mode=mode,
        )
    except ArticlePreviewError:
        raise
    except (RenderingError, TypeError, ValueError, RecursionError) as exc:
        code, message = content_error_for_rendering(exc)
        raise ArticlePreviewError(message, code=code) from None
    return AuthorArticlePreview(
        html=rendered.html,
        sanitizer_version=rendered.sanitizer_version,
        serialized_body=serialized,
        body_bytes=body_bytes,
        text_character_count=len(rendered.plain_text),
        media_count=len(referenced),
        block_start_lines=rendered.block_start_lines,
    )
