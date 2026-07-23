from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.accounts.public import is_active_author
from apps.core.events import enqueue_event
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import Clock, SystemClock

from ..events import ARTICLE_SCHEDULE_CANCELLED, ARTICLE_SCHEDULED
from ..models import Article, ArticleRevision, PublicationReviewGrant
from ..policies import author_is_content_masked
from .publication import (
    PublicationCommandError,
    _actor,
    _apply_publication,
    _article_id,
    _load_target,
    _locked_grant,
    _revision_id,
    _row_version,
    _validate_publication,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
PublicationBlocker = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    article_id: str
    revision_id: str
    scheduled_for: datetime


@dataclass(frozen=True, slots=True)
class CancelScheduleResult:
    article_id: str
    cancelled: bool
    publication_state: str


@dataclass(frozen=True, slots=True)
class ScheduledExecutionResult:
    article_id: str
    revision_id: str
    outcome: str


def _scheduled_utc(value: datetime, now: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise PublicationCommandError(
            "content.schedule_time_invalid.v1",
            "排期时间须为上海时区的本地日期时间。",
        )
    scheduled = value.replace(tzinfo=SHANGHAI).astimezone(UTC)
    if scheduled <= now:
        raise PublicationCommandError(
            "content.schedule_time_invalid.v1", "排期时间必须晚于当前时间。"
        )
    return scheduled


def _grant_matches(
    grant: PublicationReviewGrant,
    *,
    actor_id,
    article: Article,
    revision: ArticleRevision,
    now: datetime,
) -> bool:
    return (
        grant.consumed_at is None
        and grant.expires_at > now
        and grant.actor_id == actor_id
        and grant.article_id == article.id
        and grant.revision_id == revision.id
        and grant.row_version == article.row_version
    )


def schedule_article(
    *,
    actor_id,
    article_id: str,
    revision_id: str,
    expected_row_version: int,
    review_token: str,
    scheduled_local: datetime,
    trace_code: str,
    clock: Clock | None = None,
) -> ScheduleResult:
    actor = _actor(actor_id)
    article_key = _article_id(article_id)
    revision_key = _revision_id(revision_id)
    version = _row_version(expected_row_version)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    scheduled_for = _scheduled_utc(scheduled_local, now)
    with transaction.atomic():
        article, revision = _load_target(
            actor_id=actor,
            article_id=article_key,
            revision_id=revision_key,
            expected_row_version=version,
        )
        grant = _locked_grant(review_token)
        if not _grant_matches(
            grant,
            actor_id=actor,
            article=article,
            revision=revision,
            now=now,
        ):
            raise PublicationCommandError(
                "content.review_token_invalid.v1", "终稿审查已失效，请重新审查。"
            )
        _validate_publication(article, revision)
        article.publication_state = Article.PublicationState.SCHEDULED
        article.scheduled_revision = revision
        article.scheduled_for = scheduled_for
        article.scheduled_at = now
        article.save(
            update_fields=(
                "publication_state",
                "scheduled_revision",
                "scheduled_for",
                "scheduled_at",
                "updated_at",
            )
        )
        PublicationReviewGrant.objects.filter(
            article=article,
            revision=revision,
            row_version=article.row_version,
            consumed_at__isnull=True,
        ).update(consumed_at=now)
        enqueue_event(
            ARTICLE_SCHEDULED,
            aggregate_type="article",
            aggregate_id=article.id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "revision_id": revision.id,
                "scheduled_for": scheduled_for.isoformat(),
            },
            clock=active_clock,
        )
    return ScheduleResult(article.id, revision.id, scheduled_for)


def _cancel_locked(
    *, article: Article, trace_code: str, clock: Clock, outcome: str
) -> ScheduledExecutionResult:
    revision_id = article.scheduled_revision_id or article.working_revision_id or ""
    article.scheduled_revision = None
    article.scheduled_for = None
    article.scheduled_at = None
    article.publication_state = Article.PublicationState.DRAFT
    article.save(
        update_fields=(
            "scheduled_revision",
            "scheduled_for",
            "scheduled_at",
            "publication_state",
            "updated_at",
        )
    )
    enqueue_event(
        ARTICLE_SCHEDULE_CANCELLED,
        aggregate_type="article",
        aggregate_id=article.id,
        actor_id=article.author_id,
        trace_code=trace_code,
        payload={"revision_id": revision_id or None},
        clock=clock,
    )
    return ScheduledExecutionResult(article.id, revision_id, outcome)


def cancel_schedule(
    *,
    actor_id,
    article_id: str,
    trace_code: str,
    clock: Clock | None = None,
) -> CancelScheduleResult:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    active_clock = clock or SystemClock()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(
                pk=identity,
                author_id=actor,
                deleted_at__isnull=True,
            )
        except Article.DoesNotExist:
            raise PublicationCommandError(
                "content.article_not_editable.v1", "文章不存在或不可取消排期。"
            ) from None
        if (
            article.publication_state != Article.PublicationState.SCHEDULED
            or article.scheduled_revision_id is None
        ):
            return CancelScheduleResult(
                article.id,
                False,
                article.publication_state,
            )
        _cancel_locked(
            article=article,
            trace_code=trace_code,
            clock=active_clock,
            outcome="cancelled",
        )
    return CancelScheduleResult(article.id, True, article.publication_state)


def _not_blocked(_article_id: str) -> bool:
    return False


def publish_scheduled_article(
    *,
    article_id: str,
    scheduled_revision_id: str,
    publication_blocker: PublicationBlocker = _not_blocked,
    trace_code: str | None = None,
    clock: Clock | None = None,
) -> ScheduledExecutionResult:
    identity = _article_id(article_id)
    revision_key = _revision_id(scheduled_revision_id)
    if not callable(publication_blocker):
        raise TypeError("publication_blocker must be callable")
    active_clock = clock or SystemClock()
    now = active_clock.now()
    active_trace = trace_code or new_trace_code()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(pk=identity)
        except Article.DoesNotExist:
            return ScheduledExecutionResult(identity, revision_key, "missing")
        if (
            article.publication_state != Article.PublicationState.SCHEDULED
            or article.scheduled_revision_id != revision_key
        ):
            return ScheduledExecutionResult(identity, revision_key, "stale")
        if article.scheduled_for is None or article.scheduled_for > now:
            return ScheduledExecutionResult(identity, revision_key, "not_due")
        if is_active_author(article.author_id) is False or author_is_content_masked(
            article.author_id
        ):
            return _cancel_locked(
                article=article,
                trace_code=active_trace,
                clock=active_clock,
                outcome="cancelled_author",
            )
        if article.deleted_at is not None:
            return ScheduledExecutionResult(
                article.id,
                revision_key,
                "deferred_deleted",
            )
        if publication_blocker(article.id):
            return _cancel_locked(
                article=article,
                trace_code=active_trace,
                clock=active_clock,
                outcome="cancelled_blocked",
            )
        try:
            revision = ArticleRevision.objects.get(pk=revision_key, article=article)
            _validate_publication(article, revision)
        except (ArticleRevision.DoesNotExist, PublicationCommandError):
            return _cancel_locked(
                article=article,
                trace_code=active_trace,
                clock=active_clock,
                outcome="cancelled_invalid",
            )
        _apply_publication(
            article=article,
            revision=revision,
            actor_id=article.author_id,
            trace_code=active_trace,
            now=now,
            clock=active_clock,
        )
    return ScheduledExecutionResult(identity, revision_key, "published")


def due_scheduled_articles(
    *, now: datetime, batch_size: int = 100
) -> tuple[tuple[str, str], ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1000
    ):
        raise ValueError("batch_size must be between 1 and 1000")
    return tuple(
        Article.objects.filter(
            publication_state=Article.PublicationState.SCHEDULED,
            scheduled_revision__isnull=False,
            scheduled_for__lte=now,
            deleted_at__isnull=True,
        )
        .order_by("scheduled_for", "id")
        .values_list("id", "scheduled_revision_id")[:batch_size]
    )
