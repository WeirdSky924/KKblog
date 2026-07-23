from uuid import UUID

from celery import shared_task
from django.conf import settings

from apps.core.ids import normalize_ulid
from apps.core.time.clock import SystemClock
from apps.operations.public import StartOutcome, execute_celery_entry

from ..services.scheduling import due_scheduled_articles, publish_scheduled_article


def _business_object(article_id: str, revision_id: str) -> str:
    return (
        f"article:{normalize_ulid(article_id)}:schedule:{normalize_ulid(revision_id)}"
    )


def _parse_business_object(value: str) -> tuple[str, str]:
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "article" or parts[2] != "schedule":
        raise ValueError("Invalid scheduled article business object")
    return normalize_ulid(parts[1]), normalize_ulid(parts[3])


def _scheduled_service(business_object: str) -> str:
    article_id, revision_id = _parse_business_object(business_object)
    outcome = publish_scheduled_article(
        article_id=article_id,
        scheduled_revision_id=revision_id,
    )
    return f"article:{article_id}:{outcome.outcome}"


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
    name="apps.content.publish_scheduled_article",
)
def publish_scheduled_article_task(
    self, article_id: str, revision_id: str
) -> dict[str, str]:
    business_object = _business_object(article_id, revision_id)
    result = execute_celery_entry(
        self,
        task_name="apps.content.publish_scheduled_article",
        business_object=business_object,
        idempotency_key=business_object,
        service=_scheduled_service,
    )
    return _task_response(result)


def _request_id(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid scheduled article dispatcher request ID") from None


def _dispatch_service(business_object: str) -> str:
    del business_object
    due = due_scheduled_articles(
        now=SystemClock().now(),
        batch_size=settings.CONTENT_SCHEDULE_BATCH_SIZE,
    )
    for article_id, revision_id in due:
        publish_scheduled_article_task.delay(article_id, revision_id)
    return f"queued:{len(due)}"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.content.dispatch_scheduled_articles",
)
def dispatch_scheduled_articles(self) -> dict[str, str]:
    request_id = _request_id(self)
    result = execute_celery_entry(
        self,
        task_name="apps.content.dispatch_scheduled_articles",
        business_object=f"content-schedule-dispatch:{request_id}",
        idempotency_key=f"content-schedule-dispatch:{request_id}",
        service=_dispatch_service,
    )
    return _task_response(result)
