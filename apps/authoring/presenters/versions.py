from dataclasses import dataclass
from datetime import datetime

from apps.content.public import (
    ArticlePreviewError,
    ContentFormat,
    Visibility,
    preview_article_body,
)
from apps.core.time import to_shanghai

_FORMAT_LABELS = {
    ContentFormat.MARKDOWN: "Markdown",
    ContentFormat.TIPTAP_JSON: "富文本",
}
_VISIBILITY_LABELS = {
    Visibility.PUBLIC: "大众可见",
    Visibility.AUTHENTICATED: "登录可见",
    Visibility.PRIVATE: "仅自己",
}
_CHANGE_LABELS = {
    "title": "标题",
    "body": "正文或格式",
    "cover": "封面",
    "visibility": "可见范围",
    "section": "分区",
    "tags": "标签",
    "summary": "摘要",
    "comments": "评论设置",
}


@dataclass(frozen=True, slots=True)
class VersionRow:
    revision_id: str
    sequence: int
    created_at: datetime
    format_label: str
    visibility_label: str
    is_working: bool
    is_published: bool
    is_scheduled: bool
    is_restored: bool


@dataclass(frozen=True, slots=True)
class VersionPreview:
    source_revision_id: str
    row_version: int
    restore_token: str
    title: str
    sanitized_html: str
    preview_error: str
    format_label: str
    visibility_label: str
    section_name: str
    tag_names: tuple[str, ...]
    cover_asset_id: str | None
    change_labels: tuple[str, ...]
    can_restore: bool


def version_rows(timeline) -> tuple[VersionRow, ...]:
    return tuple(
        VersionRow(
            revision_id=item.revision_id,
            sequence=item.sequence,
            created_at=to_shanghai(item.created_at),
            format_label=_FORMAT_LABELS[item.content_format],
            visibility_label=_VISIBILITY_LABELS[item.visibility],
            is_working=item.is_working,
            is_published=item.is_published,
            is_scheduled=item.is_scheduled,
            is_restored=item.restore_source_id is not None,
        )
        for item in timeline
    )


def version_preview(preview, *, can_restore: bool) -> VersionPreview:
    try:
        rendered = preview_article_body(
            content_format=preview.source.content_format,
            body=preview.source.body,
            body_asset_ids=preview.source.body_asset_ids,
        )
        html, error = rendered.html, ""
    except ArticlePreviewError as exc:
        html, error = "", exc.safe_message
    return VersionPreview(
        source_revision_id=preview.source_revision_id,
        row_version=preview.row_version,
        restore_token=preview.token,
        title=preview.source.title,
        sanitized_html=html,
        preview_error=error,
        format_label=_FORMAT_LABELS[preview.source.content_format],
        visibility_label=_VISIBILITY_LABELS[preview.source.visibility],
        section_name=preview.source_section_name,
        tag_names=preview.source_tag_names,
        cover_asset_id=preview.source.cover_asset_id,
        change_labels=tuple(_CHANGE_LABELS[item] for item in preview.changed_fields),
        can_restore=can_restore and not error,
    )
