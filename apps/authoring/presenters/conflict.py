from dataclasses import dataclass
from datetime import datetime

from apps.content.public import ContentFormat, Visibility

_FORMAT_LABELS = {
    ContentFormat.MARKDOWN: "Markdown",
    ContentFormat.TIPTAP_JSON: "富文本",
}
_VISIBILITY_LABELS = {
    Visibility.PUBLIC: "大众可见",
    Visibility.AUTHENTICATED: "登录可见",
    Visibility.PRIVATE: "仅自己",
}


@dataclass(frozen=True, slots=True)
class ConflictRevision:
    revision_id: str
    sequence: int
    created_at: datetime
    format_label: str
    visibility_label: str
    is_current: bool
    is_baseline: bool
    is_working: bool
    is_published: bool
    is_scheduled: bool
    is_restored: bool


@dataclass(frozen=True, slots=True)
class ConflictWorkspace:
    article_id: str
    baseline_revision_id: str
    current_revision_id: str
    revisions: tuple[ConflictRevision, ...]


def conflict_workspace(conflict, timeline) -> ConflictWorkspace:
    return ConflictWorkspace(
        article_id=conflict.article_id,
        baseline_revision_id=conflict.baseline.revision_id,
        current_revision_id=conflict.current.revision_id,
        revisions=tuple(
            ConflictRevision(
                revision_id=item.revision_id,
                sequence=item.sequence,
                created_at=item.created_at,
                format_label=_FORMAT_LABELS[item.content_format],
                visibility_label=_VISIBILITY_LABELS[item.visibility],
                is_current=item.revision_id == conflict.current.revision_id,
                is_baseline=item.revision_id == conflict.baseline.revision_id,
                is_working=item.is_working,
                is_published=item.is_published,
                is_scheduled=item.is_scheduled,
                is_restored=item.restore_source_id is not None,
            )
            for item in timeline
        ),
    )
