from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_active_author, is_administrator
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.media.public import MediaTargetType, release_target_assets
from apps.operations.public import record_audit_entry

from ..events import ARTICLE_DELETED, ARTICLE_PURGE_REQUESTED, ARTICLE_RESTORED
from ..models import Article, ArticleTombstone
from ..policies import article_is_reader_masked
from ..purge_ports import (
    ArticleCommentPurge,
    ArticleCommentPurgeResult,
    purge_article_comments,
)

COOLING_PERIOD = timedelta(days=7)


class ArticleDeletionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


class ArticlePurgeOutcome(StrEnum):
    PURGED = "purged"
    ALREADY_PURGED = "already_purged"
    NOT_DUE = "not_due"
    STALE = "stale"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class ArticleDeletionResult:
    article_id: str
    deleted_at: datetime
    purge_after: datetime
    row_version: int
    changed: bool


@dataclass(frozen=True, slots=True)
class ArticleRestorationResult:
    article_id: str
    publication_state: str
    row_version: int
    changed: bool


@dataclass(frozen=True, slots=True)
class ArticlePurgeResult:
    article_id: str
    outcome: ArticlePurgeOutcome
    asset_ids: tuple[str, ...] = ()
    comment_count: int = 0


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleDeletionError(
            "content.article_delete_not_allowed.v1",
            "文章不存在或不能执行该操作。",
        ) from None


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleDeletionError(
            "content.article_delete_not_allowed.v1",
            "文章不存在或不能执行该操作。",
        ) from None


def _row_version(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ArticleDeletionError(
            "content.edit_conflict.v1",
            "文章版本已发生变化。",
        )
    return value


def _aware_datetime(value, *, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _delete_allowed(article: Article, actor: UUID, administrative: bool) -> bool:
    if administrative:
        return is_administrator(actor)
    return (
        actor == article.author_id
        and is_active_author(actor)
        and not article_is_reader_masked(article.id)
    )


def delete_article(
    *,
    actor_id,
    article_id: str,
    expected_row_version: int,
    administrative: bool,
    trace_code: str,
    client_ip: str,
    clock: Clock | None = None,
) -> ArticleDeletionResult:
    actor = _actor_id(actor_id)
    identity = _article_id(article_id)
    version = _row_version(expected_row_version)
    if type(administrative) is not bool:
        raise ArticleDeletionError(
            "content.article_delete_not_allowed.v1",
            "文章不存在或不能执行该操作。",
        )
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(pk=identity)
        except Article.DoesNotExist:
            raise ArticleDeletionError(
                "content.article_delete_not_allowed.v1",
                "文章不存在或不能执行该操作。",
            ) from None
        if not _delete_allowed(article, actor, administrative):
            raise ArticleDeletionError(
                "content.article_delete_not_allowed.v1",
                "文章不存在或不能执行该操作。",
            )
        if article.deleted_at is not None and article.purge_after is not None:
            return ArticleDeletionResult(
                article.id,
                article.deleted_at,
                article.purge_after,
                article.row_version,
                False,
            )
        if article.row_version != version:
            raise ArticleDeletionError(
                "content.edit_conflict.v1",
                "文章版本已发生变化。",
            )
        purge_after = now + COOLING_PERIOD
        ArticleTombstone.objects.create(
            article_id=article.id,
            author_id=article.author_id,
            deletion_actor_id=actor,
            administrative=administrative,
            original_publication_state=article.publication_state,
            original_working_revision_id=article.working_revision_id,
            original_published_revision_id=article.published_revision_id,
            original_scheduled_revision_id=article.scheduled_revision_id,
            original_scheduled_for=article.scheduled_for,
            original_scheduled_at=article.scheduled_at,
            original_published_at=article.published_at,
            original_last_published_at=article.last_published_at,
            deleted_at=now,
            purge_after=purge_after,
        )
        article.deleted_at = now
        article.purge_after = purge_after
        article.row_version += 1
        article.save(
            update_fields=("deleted_at", "purge_after", "row_version", "updated_at")
        )
        record_audit_entry(
            action="content.article.delete",
            actor_id=actor,
            target_id=article.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"publication_state": article.publication_state},
            after={
                "administrative": administrative,
                "deleted_at": now.isoformat(),
                "purge_after": purge_after.isoformat(),
            },
            summary="Soft delete article",
        )
        enqueue_event(
            ARTICLE_DELETED,
            aggregate_type="article",
            aggregate_id=article.id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "recipient_id": str(article.author_id),
                "administrative": administrative,
                "purge_after": purge_after.isoformat(),
            },
            clock=active_clock,
        )
    return ArticleDeletionResult(
        article.id,
        now,
        purge_after,
        article.row_version,
        True,
    )


def restore_deleted_article(
    *,
    actor_id,
    article_id: str,
    expected_row_version: int,
    trace_code: str,
    client_ip: str,
    clock: Clock | None = None,
) -> ArticleRestorationResult:
    actor = _actor_id(actor_id)
    identity = _article_id(article_id)
    version = _row_version(expected_row_version)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(pk=identity)
            tombstone = ArticleTombstone.objects.select_for_update().get(
                article_id=identity,
                purged_at__isnull=True,
            )
        except (Article.DoesNotExist, ArticleTombstone.DoesNotExist):
            raise ArticleDeletionError(
                "content.article_restore_not_allowed.v1",
                "文章不存在或不能恢复。",
            ) from None
        administrator = is_administrator(actor)
        owner = actor == article.author_id and is_active_author(actor)
        if (tombstone.administrative and not administrator) or not (
            administrator or owner
        ):
            raise ArticleDeletionError(
                "content.article_restore_not_allowed.v1",
                "文章不存在或不能恢复。",
            )
        if article.deleted_at is None or article.purge_after is None:
            raise ArticleDeletionError(
                "content.article_restore_not_allowed.v1",
                "文章不存在或不能恢复。",
            )
        if now >= article.purge_after:
            raise ArticleDeletionError(
                "content.article_restore_expired.v1",
                "文章恢复期限已结束。",
            )
        if article.row_version != version:
            raise ArticleDeletionError(
                "content.edit_conflict.v1",
                "文章版本已发生变化。",
            )
        article.publication_state = tombstone.original_publication_state
        article.working_revision_id = tombstone.original_working_revision_id
        article.published_revision_id = tombstone.original_published_revision_id
        article.scheduled_revision_id = tombstone.original_scheduled_revision_id
        article.scheduled_for = tombstone.original_scheduled_for
        article.scheduled_at = tombstone.original_scheduled_at
        article.published_at = tombstone.original_published_at
        article.last_published_at = tombstone.original_last_published_at
        article.deleted_at = None
        article.purge_after = None
        article.row_version += 1
        article.save(
            update_fields=(
                "publication_state",
                "working_revision",
                "published_revision",
                "scheduled_revision",
                "scheduled_for",
                "scheduled_at",
                "published_at",
                "last_published_at",
                "deleted_at",
                "purge_after",
                "row_version",
                "updated_at",
            )
        )
        administrative = actor != article.author_id
        record_audit_entry(
            action="content.article.restore",
            actor_id=actor,
            target_id=article.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={
                "administrative": tombstone.administrative,
                "deleted_at": tombstone.deleted_at.isoformat(),
                "purge_after": tombstone.purge_after.isoformat(),
            },
            after={
                "restored": True,
                "publication_state": article.publication_state,
            },
            summary="Restore soft-deleted article",
        )
        enqueue_event(
            ARTICLE_RESTORED,
            aggregate_type="article",
            aggregate_id=article.id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "recipient_id": str(article.author_id),
                "administrative": administrative,
            },
            clock=active_clock,
        )
        tombstone.delete()
    return ArticleRestorationResult(
        article.id,
        article.publication_state,
        article.row_version,
        True,
    )


def due_deleted_articles(
    *,
    now: datetime,
    batch_size: int = 100,
) -> tuple[tuple[str, datetime], ...]:
    active_now = _aware_datetime(now, field="now")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1_000
    ):
        raise ValueError("batch_size must be between 1 and 1000")
    with transaction.atomic():
        return tuple(
            Article.objects.select_for_update(skip_locked=True)
            .filter(
                deleted_at__isnull=False,
                purge_after__isnull=False,
                purge_after__lte=active_now,
            )
            .order_by("purge_after", "id")
            .values_list("id", "purge_after")[:batch_size]
        )


def purge_deleted_article(
    *,
    article_id: str,
    expected_purge_after: datetime,
    clock: Clock | None = None,
    storage=None,
    comment_purge: ArticleCommentPurge | None = None,
) -> ArticlePurgeResult:
    identity = _article_id(article_id)
    deadline = _aware_datetime(expected_purge_after, field="expected_purge_after")
    if comment_purge is not None and not callable(comment_purge):
        raise TypeError("comment_purge must be callable")
    active_clock = clock or SystemClock()
    now = active_clock.now()
    purge_comments: Callable[[str], ArticleCommentPurgeResult] = (
        comment_purge or purge_article_comments
    )
    with transaction.atomic():
        article = Article.objects.select_for_update().filter(pk=identity).first()
        tombstone = (
            ArticleTombstone.objects.select_for_update()
            .filter(article_id=identity)
            .first()
        )
        if article is None:
            if (
                tombstone is not None
                and tombstone.purged_at is not None
                and tombstone.purge_after == deadline
            ):
                return ArticlePurgeResult(
                    identity,
                    ArticlePurgeOutcome.ALREADY_PURGED,
                )
            return ArticlePurgeResult(identity, ArticlePurgeOutcome.MISSING)
        if (
            tombstone is None
            or article.deleted_at is None
            or article.purge_after is None
            or article.purge_after != deadline
            or tombstone.purge_after != deadline
        ):
            return ArticlePurgeResult(identity, ArticlePurgeOutcome.STALE)
        if now < deadline:
            return ArticlePurgeResult(identity, ArticlePurgeOutcome.NOT_DUE)

        comment_result = purge_comments(identity)
        if not isinstance(comment_result, ArticleCommentPurgeResult):
            raise TypeError("comment_purge returned an invalid result")
        revision_ids = tuple(
            article.revisions.order_by("id").values_list("id", flat=True)
        )
        if revision_ids:
            media_result = release_target_assets(
                target_type=MediaTargetType.ARTICLE_REVISION,
                target_ids=revision_ids,
                storage=storage,
            )
            asset_ids = media_result.asset_ids
        else:
            asset_ids = ()
        tombstone.purged_at = now
        tombstone.save(update_fields=("purged_at", "updated_at"))
        enqueue_event(
            ARTICLE_PURGE_REQUESTED,
            aggregate_type="article",
            aggregate_id=identity,
            payload={
                "asset_count": len(asset_ids),
                "comment_count": comment_result.comment_count,
            },
            clock=active_clock,
        )
        article.delete()
    return ArticlePurgeResult(
        identity,
        ArticlePurgeOutcome.PURGED,
        asset_ids,
        comment_result.comment_count,
    )
