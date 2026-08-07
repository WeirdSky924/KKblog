from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.content.public import AuthorArticlePage, author_article_page
from apps.core.time import to_shanghai
from apps.core.time.clock import Clock

_STATE_LABELS = {
    "PUBLISHED": "已发布",
    "DRAFT": "草稿",
    "SCHEDULED": "定时发布",
    "DELETED": "删除冷静期",
}
_VISIBILITY_LABELS = {
    "PUBLIC": "大众",
    "AUTHENTICATED": "登录可见",
    "PRIVATE": "仅自己",
}
_FORMAT_LABELS = {"MARKDOWN": "Markdown", "TIPTAP_JSON": "富文本"}


@dataclass(frozen=True, slots=True)
class WorkspaceTab:
    state: str
    label: str
    count: int
    selected: bool


@dataclass(frozen=True, slots=True)
class WorkspaceArticle:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    state: str
    state_label: str
    visibility_label: str
    format_label: str
    cover_asset_id: str | None
    sequence: int
    timing_label: str
    timing_value: datetime
    row_version: int
    has_unpublished_changes: bool
    can_edit: bool
    can_review: bool
    can_restore: bool
    can_delete: bool


@dataclass(frozen=True, slots=True)
class ArticleWorkspace:
    tabs: tuple[WorkspaceTab, ...]
    articles: tuple[WorkspaceArticle, ...]
    selected_state: str
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool


def _timing(item) -> tuple[str, datetime]:
    if item.state == "PUBLISHED" and item.published_at is not None:
        return "发布", item.published_at
    if item.state == "SCHEDULED" and item.scheduled_for is not None:
        return "计划", item.scheduled_for
    if item.state == "DELETED" and item.purge_after is not None:
        return "清理期限", item.purge_after
    return "更新", item.updated_at


def _article(item) -> WorkspaceArticle:
    timing_label, timing_value = _timing(item)
    return WorkspaceArticle(
        article_id=item.article_id,
        revision_id=item.revision_id,
        author_id=item.author_id,
        title=item.title,
        state=item.state,
        state_label=_STATE_LABELS[item.state],
        visibility_label=_VISIBILITY_LABELS[item.visibility],
        format_label=_FORMAT_LABELS[item.content_format],
        cover_asset_id=item.cover_asset_id,
        sequence=item.sequence,
        timing_label=timing_label,
        timing_value=to_shanghai(timing_value),
        row_version=item.row_version,
        has_unpublished_changes=item.has_unpublished_changes,
        can_edit=item.can_edit,
        can_review=item.can_review,
        can_restore=item.can_restore,
        can_delete=item.can_delete,
    )


def _workspace(source: AuthorArticlePage) -> ArticleWorkspace:
    tabs = tuple(
        WorkspaceTab(
            state=state,
            label=label,
            count=source.counts.for_state(state),
            selected=source.selected_state == state,
        )
        for state, label in _STATE_LABELS.items()
    )
    return ArticleWorkspace(
        tabs=tabs,
        articles=tuple(_article(item) for item in source.items),
        selected_state=source.selected_state,
        page_number=source.page_number,
        page_size=source.page_size,
        total_items=source.total_items,
        total_pages=source.total_pages,
        has_previous=source.has_previous,
        has_next=source.has_next,
    )


def article_workspace(
    *,
    actor_id,
    state: str = "PUBLISHED",
    page: int = 1,
    page_size: int = 20,
    clock: Clock | None = None,
) -> ArticleWorkspace:
    return _workspace(
        author_article_page(
            actor_id=actor_id,
            state=state,
            page=page,
            page_size=page_size,
            clock=clock,
        )
    )
