from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.public import is_active_author
from apps.core.ids import normalize_ulid
from apps.core.pagination import PageSlice
from apps.core.time.clock import Clock, SystemClock

from ..block_changes import BlockChangeSummary, project_article_block_changes
from ..models import Article, ArticleRevision
from ..policies import author_is_content_masked
from .access import ArticleNotFound


@dataclass(frozen=True, slots=True)
class RevisionTimelineItem:
    revision_id: str
    sequence: int
    created_at: datetime
    content_format: str
    visibility: str
    based_on_id: str | None
    restore_source_id: str | None
    is_working: bool
    is_published: bool
    is_scheduled: bool


def revision_timeline(
    *,
    actor_id,
    article_id: str,
    clock: Clock | None = None,
    page: int | None = None,
    page_size: int = 20,
) -> tuple[RevisionTimelineItem, ...] | PageSlice[RevisionTimelineItem]:
    try:
        actor = UUID(str(actor_id))
        identity = normalize_ulid(article_id)
    except (TypeError, ValueError):
        raise ArticleNotFound from None
    if not is_active_author(actor) or author_is_content_masked(actor):
        raise ArticleNotFound
    now = (clock or SystemClock()).now()
    try:
        article = Article.objects.get(
            Q(deleted_at__isnull=True) | Q(purge_after__gt=now),
            pk=identity,
            author_id=actor,
        )
    except Article.DoesNotExist:
        raise ArticleNotFound from None
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("revision page is invalid")
    ordered = ArticleRevision.objects.filter(article=article).order_by("-sequence")

    def item(revision: ArticleRevision) -> RevisionTimelineItem:
        return RevisionTimelineItem(
            revision.id,
            revision.sequence,
            revision.created_at,
            revision.content_format,
            revision.visibility,
            revision.based_on_id,
            revision.restore_source_id,
            revision.id == article.working_revision_id,
            revision.id == article.published_revision_id,
            revision.id == article.scheduled_revision_id,
        )

    if page is None:
        return tuple(item(revision) for revision in ordered)
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(item(revision) for revision in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def revision_block_changes(
    *,
    actor_id,
    article_id: str,
    before_revision_id: str,
    after_revision_id: str,
    clock: Clock | None = None,
) -> BlockChangeSummary:
    try:
        actor = UUID(str(actor_id))
        identity = normalize_ulid(article_id)
        before_id = normalize_ulid(before_revision_id)
        after_id = normalize_ulid(after_revision_id)
    except (TypeError, ValueError):
        raise ArticleNotFound from None
    if not is_active_author(actor) or author_is_content_masked(actor):
        raise ArticleNotFound
    now = (clock or SystemClock()).now()
    try:
        article = Article.objects.get(
            Q(deleted_at__isnull=True) | Q(purge_after__gt=now),
            pk=identity,
            author_id=actor,
        )
        revisions = {
            revision.id: revision
            for revision in ArticleRevision.objects.filter(
                article=article,
                pk__in=(before_id, after_id),
            )
        }
        before = revisions[before_id]
        after = revisions[after_id]
    except (Article.DoesNotExist, KeyError):
        raise ArticleNotFound from None
    before_body = (
        before.body_markdown
        if before.content_format == ArticleRevision.ContentFormat.MARKDOWN
        else before.body_tiptap
    )
    after_body = (
        after.body_markdown
        if after.content_format == ArticleRevision.ContentFormat.MARKDOWN
        else after.body_tiptap
    )
    assert before_body is not None and after_body is not None
    return project_article_block_changes(
        before_content_format=before.content_format,
        before_body=before_body,
        before_schema_version=before.tiptap_schema_version,
        after_content_format=after.content_format,
        after_body=after_body,
        after_schema_version=after.tiptap_schema_version,
    )
