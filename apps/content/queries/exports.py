from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.core.ids import normalize_ulid
from apps.media.public import render_tiptap

from ..models import Article, ArticleRevision
from .discovery import sanitized_article_plain_text


class ContentExportError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class ExportArticleSnapshot:
    article_id: str
    author_id: UUID
    publication_state: str
    visibility: str
    section_id: UUID | None
    revision_ids: tuple[str, ...]
    working_revision_id: str | None
    published_revision_id: str | None
    scheduled_revision_id: str | None
    scheduled_for: datetime | None
    published_at: datetime | None
    deleted_at: datetime | None
    purge_after: datetime | None


@dataclass(frozen=True, slots=True)
class ExportRevisionTag:
    tag_id: UUID
    name: str
    state: str


@dataclass(frozen=True, slots=True)
class ExportRevisionPayload:
    revision_id: str
    article_id: str
    sequence: int
    based_on_id: str | None
    restore_source_id: str | None
    content_format: str
    title: str
    body_markdown: str | None
    body_tiptap: dict | None
    convenience_markdown: str
    summary_mode: str
    custom_summary: str | None
    visibility: str
    section_id: UUID | None
    section_name: str | None
    cover_asset_id: str | None
    comments_enabled: bool
    comments_view_login: bool
    comments_post_login: bool
    created_by_id: UUID
    reason: str
    created_at: datetime
    tags: tuple[ExportRevisionTag, ...]


def _uuid(value: UUID | str | None, *, code: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ContentExportError(code, "导出筛选条件无效。") from None


def _article_ids(values) -> tuple[str, ...]:
    if isinstance(values, str | bytes) or values is None:
        raise ContentExportError(
            "exchange.export_scope_invalid.v1", "导出文章选择无效。"
        )
    try:
        return tuple(dict.fromkeys(normalize_ulid(value) for value in values))
    except (TypeError, ValueError):
        raise ContentExportError(
            "exchange.export_scope_invalid.v1", "导出文章选择无效。"
        ) from None


def _current_revision(article: Article) -> ArticleRevision:
    revision = (
        article.working_revision
        or article.scheduled_revision
        or article.published_revision
    )
    if revision is None:
        raise ContentExportError(
            "exchange.export_article_invalid.v1", "导出文章缺少有效修订。"
        )
    return revision


def export_article_snapshots(
    *,
    scope: str,
    scope_author_id: UUID | str | None,
    scope_section_id: UUID | str | None,
    article_ids,
) -> tuple[ExportArticleSnapshot, ...]:
    queryset = Article.objects.select_related(
        "working_revision",
        "published_revision",
        "scheduled_revision",
    ).prefetch_related("revisions")
    requested_ids: tuple[str, ...] = ()
    if scope == "ALL":
        pass
    elif scope == "AUTHOR":
        queryset = queryset.filter(
            author_id=_uuid(
                scope_author_id,
                code="exchange.export_scope_invalid.v1",
            )
        )
    elif scope == "SECTION":
        queryset = queryset.filter(
            working_revision__section_id=_uuid(
                scope_section_id,
                code="exchange.export_scope_invalid.v1",
            )
        )
    elif scope == "ARTICLES":
        requested_ids = _article_ids(article_ids)
        queryset = queryset.filter(pk__in=requested_ids)
    else:
        raise ContentExportError("exchange.export_scope_invalid.v1", "导出范围无效。")

    articles = tuple(queryset.order_by("id"))
    if requested_ids and {article.id for article in articles} != set(requested_ids):
        raise ContentExportError(
            "exchange.export_article_not_found.v1", "部分导出文章不存在。"
        )
    snapshots = []
    for article in articles:
        current = _current_revision(article)
        revision_ids = tuple(
            revision.id
            for revision in sorted(
                article.revisions.all(), key=lambda row: row.sequence
            )
        )
        if not revision_ids:
            raise ContentExportError(
                "exchange.export_article_invalid.v1", "导出文章缺少有效修订。"
            )
        snapshots.append(
            ExportArticleSnapshot(
                article_id=article.id,
                author_id=article.author_id,
                publication_state=article.publication_state,
                visibility=current.visibility,
                section_id=current.section_id,
                revision_ids=revision_ids,
                working_revision_id=article.working_revision_id,
                published_revision_id=article.published_revision_id,
                scheduled_revision_id=article.scheduled_revision_id,
                scheduled_for=article.scheduled_for,
                published_at=article.published_at,
                deleted_at=article.deleted_at,
                purge_after=article.purge_after,
            )
        )
    return tuple(snapshots)


def export_revision_payloads(*, revision_ids) -> tuple[ExportRevisionPayload, ...]:
    if revision_ids is None or isinstance(revision_ids, str | bytes):
        raise ContentExportError(
            "exchange.export_revision_invalid.v1", "导出修订选择无效。"
        )
    try:
        identities = tuple(
            dict.fromkeys(normalize_ulid(revision_id) for revision_id in revision_ids)
        )
    except (TypeError, ValueError):
        raise ContentExportError(
            "exchange.export_revision_invalid.v1", "导出修订选择无效。"
        ) from None
    if not identities:
        return ()
    rows = {
        revision.id: revision
        for revision in ArticleRevision.objects.filter(pk__in=identities)
        .select_related("section")
        .prefetch_related("tag_snapshots__tag")
    }
    if set(rows) != set(identities):
        raise ContentExportError(
            "exchange.export_revision_missing.v1", "导出修订已不存在。"
        )
    payloads = []
    for revision_id in identities:
        revision = rows[revision_id]
        tiptap_source = (
            deepcopy(revision.body_tiptap)
            if revision.content_format == ArticleRevision.ContentFormat.TIPTAP_JSON
            else None
        )
        convenience_markdown = revision.body_markdown or ""
        if tiptap_source is not None:
            convenience_markdown = sanitized_article_plain_text(
                render_tiptap(tiptap_source).html
            )
        tags = tuple(
            ExportRevisionTag(item.tag_id, item.tag.name, item.tag.state)
            for item in sorted(
                revision.tag_snapshots.all(),
                key=lambda item: (item.tag.normalized_name, str(item.tag_id)),
            )
        )
        payloads.append(
            ExportRevisionPayload(
                revision_id=revision.id,
                article_id=revision.article_id,
                sequence=revision.sequence,
                based_on_id=revision.based_on_id,
                restore_source_id=revision.restore_source_id,
                content_format=revision.content_format,
                title=revision.title,
                body_markdown=revision.body_markdown,
                body_tiptap=tiptap_source,
                convenience_markdown=convenience_markdown,
                summary_mode=revision.summary_mode,
                custom_summary=revision.custom_summary,
                visibility=revision.visibility,
                section_id=revision.section_id,
                section_name=revision.section.name if revision.section else None,
                cover_asset_id=revision.cover_asset_id,
                comments_enabled=revision.comments_enabled,
                comments_view_login=revision.comments_view_login,
                comments_post_login=revision.comments_post_login,
                created_by_id=revision.created_by_id,
                reason=revision.reason,
                created_at=revision.created_at,
                tags=tags,
            )
        )
    return tuple(payloads)
