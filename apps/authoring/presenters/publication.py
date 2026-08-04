from dataclasses import dataclass
from datetime import datetime

from apps.content.public import ContentFormat, SummaryMode, Visibility
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
_SUMMARY_LABELS = {
    SummaryMode.AUTO: "自动摘要",
    SummaryMode.CUSTOM: "自定义摘要",
    SummaryMode.NONE: "不显示摘要",
}


@dataclass(frozen=True, slots=True)
class PublicationReviewPage:
    article_id: str
    revision_id: str
    row_version: int
    review_token: str
    expires_at: datetime
    title: str
    sanitized_html: str
    format_label: str
    summary_label: str
    custom_summary: str | None
    visibility_label: str
    section_name: str
    tag_names: tuple[str, ...]
    cover_asset_id: str | None
    attachment_asset_id: str | None
    comments_label: str
    first_publication: bool


def _comments_label(review) -> str:
    if not review.comments_enabled:
        return "评论已关闭"
    rules = []
    if review.comments_view_login:
        rules.append("登录后查看")
    if review.comments_post_login:
        rules.append("登录后发表")
    return "评论开放" if not rules else "评论开放 · " + " · ".join(rules)


def publication_review_page(*, article_id: str, review) -> PublicationReviewPage:
    return PublicationReviewPage(
        article_id=article_id,
        revision_id=review.revision_id,
        row_version=review.row_version,
        review_token=review.token,
        expires_at=to_shanghai(review.expires_at),
        title=review.title,
        sanitized_html=review.sanitized_html,
        format_label=_FORMAT_LABELS[review.content_format],
        summary_label=_SUMMARY_LABELS[review.summary_mode],
        custom_summary=review.custom_summary,
        visibility_label=_VISIBILITY_LABELS[review.visibility],
        section_name=review.section_name,
        tag_names=review.tag_names,
        cover_asset_id=review.cover_asset_id,
        attachment_asset_id=review.attachment_asset_id,
        comments_label=_comments_label(review),
        first_publication=review.first_publication,
    )
