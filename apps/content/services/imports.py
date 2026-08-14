from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from django.db import transaction

from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.media.public import MediaBindingError

from ..events import ARTICLE_PUBLISHED, ARTICLE_SCHEDULED
from ..models import Article, ArticleRevision, Tag
from ..policies import article_is_reader_masked
from ..snapshots import ArticleBodyLimit, ArticleSnapshot, ContentFormat
from .articles import (
    CapacityCheck,
    ContentCommandError,
    _actor_id,
    _bind_media,
    _create_revision,
    _lock_snapshot_tags,
    _require_author,
    _run_capacity_check,
    _validate_snapshot,
    _write_tag_snapshot,
)
from .publication import PublicationCommandError, _render_for_publication
from .publication_history import record_article_publication
from .tags import TagCommandError, resolve_proposed_tags


class ImportOperation(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"


class ImportPublicationStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    SCHEDULED = "SCHEDULED"


class ImportArticleError(ValueError):
    def __init__(self, code: str, message: str = "导入文章写入失败。") -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ImportArticleCommand:
    import_key: str
    operation: ImportOperation | str
    article_id: str
    title: str
    body_markdown: str
    visibility: str = "PUBLIC"
    summary_mode: str = "AUTO"
    custom_summary: str | None = None
    section_id: UUID | str | None = None
    tag_ids: tuple[UUID | str, ...] = ()
    proposed_tag_names: tuple[str, ...] = ()
    cover_asset_id: str | None = None
    body_asset_ids: tuple[str, ...] = ()
    comments_enabled: bool = True
    comments_view_login: bool = False
    comments_post_login: bool = False
    publication_status: ImportPublicationStatus | str = ImportPublicationStatus.DRAFT
    scheduled_for: datetime | str | None = None
    published_at: datetime | str | None = None


@dataclass(frozen=True, slots=True)
class ImportArticleResult:
    article_id: str
    revision_id: str
    row_version: int
    created: bool
    format_changed: bool
    publication_status: str


def _import_key(value: str) -> str:
    if not isinstance(value, str):
        raise ImportArticleError("content.import_key_invalid.v1")
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "import":
        raise ImportArticleError("content.import_key_invalid.v1")
    try:
        normalize_ulid(parts[1])
        normalize_ulid(parts[2])
    except (TypeError, ValueError):
        raise ImportArticleError("content.import_key_invalid.v1") from None
    return value


def _article_id(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ImportArticleError("content.import_article_invalid.v1") from None


def _aware_datetime(value: datetime | str | None, *, code: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ImportArticleError(code) from None
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ImportArticleError(code)
    return value


def _existing_result(*, import_key: str, actor_id: UUID) -> ImportArticleResult | None:
    revision = (
        ArticleRevision.objects.select_related("article")
        .filter(import_key=import_key, article__author_id=actor_id)
        .first()
    )
    if revision is None:
        return None
    article = revision.article
    return ImportArticleResult(
        article.id,
        revision.id,
        article.row_version,
        revision.sequence == 1,
        revision.reason == ArticleRevision.Reason.IMPORT_FORMAT_CHANGE,
        article.publication_state,
    )


def imported_article_result(*, actor_id, import_key: str) -> ImportArticleResult | None:
    actor = _actor_id(actor_id)
    _require_author(actor)
    return _existing_result(import_key=_import_key(import_key), actor_id=actor)


def _proposed_tags(*, actor_id: UUID, names: tuple[str, ...]) -> tuple[Tag, ...]:
    try:
        tag_ids = resolve_proposed_tags(actor_id=actor_id, names=names)
    except TagCommandError as exc:
        raise ImportArticleError(
            "content.import_tag_unavailable.v1", exc.safe_message
        ) from None
    tags = {
        tag.id: tag for tag in Tag.objects.select_for_update().filter(pk__in=tag_ids)
    }
    if len(tags) != len(tag_ids):
        raise ImportArticleError("content.import_tag_unavailable.v1")
    return tuple(tags[tag_id] for tag_id in tag_ids)


def _publication_status(value: str) -> ImportPublicationStatus:
    try:
        return ImportPublicationStatus(value)
    except (TypeError, ValueError):
        raise ImportArticleError("content.import_status_invalid.v1") from None


def _validate_publishable(revision: ArticleRevision) -> None:
    revision_tags = tuple(revision.tag_snapshots.select_related("tag"))
    if len(revision_tags) > 10 or any(
        item.tag.state in {Tag.State.REJECTED, Tag.State.DELETED}
        for item in revision_tags
    ):
        raise ImportArticleError("content.import_tag_unavailable.v1")
    _render_for_publication(revision)


def _apply_imported_publication(
    *,
    article: Article,
    revision: ArticleRevision,
    status: ImportPublicationStatus,
    scheduled_for: datetime | None,
    published_at: datetime | None,
    actor_id: UUID,
    trace_code: str,
    clock: Clock,
) -> None:
    now = clock.now()
    if status == ImportPublicationStatus.DRAFT:
        article.publication_state = Article.PublicationState.DRAFT
        article.scheduled_revision = None
        article.scheduled_for = None
        article.scheduled_at = None
        return
    _validate_publishable(revision)
    if status == ImportPublicationStatus.SCHEDULED:
        if scheduled_for is None or scheduled_for <= now:
            raise ImportArticleError("content.import_schedule_invalid.v1")
        article.publication_state = Article.PublicationState.SCHEDULED
        article.scheduled_revision = revision
        article.scheduled_for = scheduled_for
        article.scheduled_at = now
        enqueue_event(
            ARTICLE_SCHEDULED,
            aggregate_type="article",
            aggregate_id=article.id,
            actor_id=actor_id,
            trace_code=trace_code,
            payload={
                "revision_id": revision.id,
                "scheduled_for": scheduled_for.isoformat(),
            },
            clock=clock,
        )
        return
    first = article.published_revision_id is None
    publication_time = published_at or now
    article.publication_state = Article.PublicationState.PUBLISHED
    article.published_revision = revision
    article.scheduled_revision = None
    article.scheduled_for = None
    article.scheduled_at = None
    if first:
        article.published_at = publication_time
    article.last_published_at = publication_time
    enqueue_event(
        ARTICLE_PUBLISHED,
        aggregate_type="article",
        aggregate_id=article.id,
        actor_id=actor_id,
        trace_code=trace_code,
        payload={"revision_id": revision.id, "first": first},
        clock=clock,
    )


def import_article_item(
    *,
    actor_id,
    command: ImportArticleCommand,
    trace_code: str,
    body_limit: ArticleBodyLimit | None = None,
    capacity_check: CapacityCheck | None = None,
    clock: Clock | None = None,
) -> ImportArticleResult:
    actor = _actor_id(actor_id)
    _require_author(actor)
    _run_capacity_check(capacity_check)
    if not isinstance(command, ImportArticleCommand):
        raise TypeError("command must be an ImportArticleCommand")
    key = _import_key(command.import_key)
    identity = _article_id(command.article_id)
    try:
        operation = ImportOperation(command.operation)
    except (TypeError, ValueError):
        raise ImportArticleError("content.import_operation_invalid.v1") from None
    status = _publication_status(command.publication_status)
    scheduled_for = _aware_datetime(
        command.scheduled_for,
        code="content.import_schedule_invalid.v1",
    )
    published_at = _aware_datetime(
        command.published_at,
        code="content.import_published_at_invalid.v1",
    )
    if status != ImportPublicationStatus.SCHEDULED and scheduled_for is not None:
        raise ImportArticleError("content.import_schedule_invalid.v1")
    snapshot = ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title=command.title,
        body=command.body_markdown,
        summary_mode=command.summary_mode,
        custom_summary=command.custom_summary,
        visibility=command.visibility,
        section_id=command.section_id,
        tag_ids=command.tag_ids,
        cover_asset_id=command.cover_asset_id,
        body_asset_ids=command.body_asset_ids,
        comments_enabled=command.comments_enabled,
        comments_view_login=command.comments_view_login,
        comments_post_login=command.comments_post_login,
    )
    try:
        validated = _validate_snapshot(snapshot, body_limit)
    except ContentCommandError as exc:
        raise ImportArticleError(exc.code, exc.safe_message) from None
    active_clock = clock or SystemClock()

    existing = _existing_result(import_key=key, actor_id=actor)
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            existing = _existing_result(import_key=key, actor_id=actor)
            if existing is not None:
                return existing
            created = operation == ImportOperation.CREATE
            if created:
                if Article.objects.filter(pk=identity).exists():
                    raise ImportArticleError("content.import_id_conflict.v1")
                article = Article.objects.create(
                    id=identity,
                    author_id=actor,
                    row_version=1,
                )
                based_on = None
                sequence = 1
                format_changed = False
            else:
                article = (
                    Article.objects.select_for_update()
                    .filter(pk=identity, author_id=actor, deleted_at__isnull=True)
                    .first()
                )
                if article is None or article_is_reader_masked(article.id):
                    raise ImportArticleError("content.import_article_not_editable.v1")
                based_on = article.working_revision
                if based_on is None:
                    raise ImportArticleError("content.import_article_not_editable.v1")
                sequence = (
                    article.revisions.order_by("-sequence")
                    .values_list("sequence", flat=True)
                    .first()
                    + 1
                )
                format_changed = (
                    based_on.content_format != ArticleRevision.ContentFormat.MARKDOWN
                )

            proposed = _proposed_tags(
                actor_id=actor,
                names=tuple(command.proposed_tag_names),
            )
            all_tag_ids = tuple(
                dict.fromkeys((*validated.tag_ids, *(tag.id for tag in proposed)))
            )
            if len(all_tag_ids) > 10:
                raise ImportArticleError("content.import_tags_invalid.v1")
            tags = _lock_snapshot_tags(actor_id=actor, tag_ids=all_tag_ids)
            revision = _create_revision(
                article=article,
                actor_id=actor,
                sequence=sequence,
                snapshot=validated,
                based_on=based_on,
                reason=(
                    ArticleRevision.Reason.IMPORT_FORMAT_CHANGE
                    if format_changed
                    else ArticleRevision.Reason.IMPORT
                ),
                import_key=key,
            )
            _write_tag_snapshot(article=article, revision=revision, tags=tags)
            _bind_media(actor_id=actor, revision=revision, snapshot=validated)
            article.working_revision = revision
            if not created:
                article.row_version += 1
            _apply_imported_publication(
                article=article,
                revision=revision,
                status=status,
                scheduled_for=scheduled_for,
                published_at=published_at,
                actor_id=actor,
                trace_code=trace_code,
                clock=active_clock,
            )
            article.save(
                update_fields=(
                    "working_revision",
                    "row_version",
                    "publication_state",
                    "published_revision",
                    "scheduled_revision",
                    "scheduled_for",
                    "scheduled_at",
                    "published_at",
                    "last_published_at",
                    "updated_at",
                )
            )
            if status == ImportPublicationStatus.PUBLISHED:
                assert article.last_published_at is not None
                record_article_publication(
                    article=article,
                    revision=revision,
                    published_at=article.last_published_at,
                )
    except ImportArticleError:
        raise
    except (ContentCommandError, MediaBindingError, PublicationCommandError) as exc:
        raise ImportArticleError(exc.code, exc.safe_message) from None
    return ImportArticleResult(
        article.id,
        revision.id,
        article.row_version,
        created,
        format_changed,
        article.publication_state,
    )
