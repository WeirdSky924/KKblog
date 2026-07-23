from datetime import UTC, datetime
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.content.purge_ports import ArticleCommentPurgeUnavailable
from apps.content.services.deletion import (
    ArticlePurgeOutcome,
    due_deleted_articles,
    purge_deleted_article,
)
from apps.core.ids import normalize_ulid
from apps.operations.public import (
    RetryableTaskError,
    StartOutcome,
    execute_celery_entry,
)


def _deadline(value: int) -> tuple[int, datetime]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Invalid article purge deadline")
    seconds, microseconds = divmod(value, 1_000_000)
    try:
        parsed = datetime.fromtimestamp(seconds, UTC).replace(microsecond=microseconds)
    except (OSError, OverflowError, ValueError):
        raise ValueError("Invalid article purge deadline") from None
    return value, parsed


def _business_object(article_id: str, deadline_us: int) -> str:
    identity = normalize_ulid(article_id)
    normalized_deadline, _ = _deadline(deadline_us)
    return f"article:{identity}:purge:{normalized_deadline}"


def _parse_business_object(value: str) -> tuple[str, int, datetime]:
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "article" or parts[2] != "purge":
        raise ValueError("Invalid article purge business object")
    article_id = normalize_ulid(parts[1])
    try:
        deadline_us = int(parts[3])
    except ValueError:
        raise ValueError("Invalid article purge business object") from None
    normalized, deadline = _deadline(deadline_us)
    return article_id, normalized, deadline


def _purge_service(business_object: str) -> str:
    article_id, _, deadline = _parse_business_object(business_object)
    try:
        result = purge_deleted_article(
            article_id=article_id,
            expected_purge_after=deadline,
        )
    except ArticleCommentPurgeUnavailable as error:
        raise RetryableTaskError(error.error_code) from None
    if result.outcome == ArticlePurgeOutcome.NOT_DUE:
        raise RetryableTaskError("content.article_purge_not_due.v1")
    return f"article:{article_id}:{result.outcome.value}"


def _task_response(result) -> dict[str, str]:
    if result.outcome == StartOutcome.ALREADY_SUCCEEDED:
        status = "already_succeeded"
    elif result.result_ref.startswith("queued:"):
        status = "queued"
    else:
        status = result.result_ref.rsplit(":", 1)[-1] if result.result_ref else "ok"
    return {"status": status}


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.content.purge_deleted_article",
)
def purge_deleted_article_task(
    self,
    article_id: str,
    deadline_us: int,
) -> dict[str, str]:
    business_object = _business_object(article_id, deadline_us)
    result = execute_celery_entry(
        self,
        task_name="apps.content.purge_deleted_article",
        business_object=business_object,
        idempotency_key=business_object,
        service=_purge_service,
    )
    return _task_response(result)


def _request_id(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid article purge dispatcher request ID") from None


def _deadline_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Article purge deadline must be timezone-aware")
    return int(value.timestamp()) * 1_000_000 + value.microsecond


def _dispatch_service(business_object: str) -> str:
    del business_object
    rows = due_deleted_articles(
        now=timezone.now(),
        batch_size=settings.CONTENT_PURGE_BATCH_SIZE,
    )
    for article_id, deadline in rows:
        purge_deleted_article_task.delay(article_id, _deadline_us(deadline))
    return f"queued:{len(rows)}"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.content.dispatch_deleted_articles",
)
def dispatch_deleted_articles(self) -> dict[str, str]:
    request_id = _request_id(self)
    result = execute_celery_entry(
        self,
        task_name="apps.content.dispatch_deleted_articles",
        business_object=f"article-purge-dispatch:{request_id}",
        idempotency_key=f"article-purge-dispatch:{request_id}",
        service=_dispatch_service,
    )
    return _task_response(result)
