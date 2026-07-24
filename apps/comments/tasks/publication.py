from uuid import UUID

from celery import shared_task
from django.conf import settings

from apps.core.ids import normalize_ulid
from apps.core.time.clock import SystemClock
from apps.operations.public import StartOutcome, execute_celery_entry

from ..services.publication import due_buffered_comment_ids, publish_due_comment


def _business_object(comment_id: str) -> str:
    return f"comment:{normalize_ulid(comment_id)}"


def _comment_from_business_object(value: str) -> str:
    prefix, separator, comment_id = value.partition(":")
    if prefix != "comment" or separator != ":":
        raise ValueError("Invalid comment publication business object")
    return normalize_ulid(comment_id)


def _publication_service(business_object: str) -> str:
    comment_id = _comment_from_business_object(business_object)
    outcome = publish_due_comment(
        comment_id=comment_id,
        now=SystemClock().now(),
    )
    return f"comment:{comment_id}:{outcome.outcome.value}"


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
    name="apps.comments.publish_due_comment",
)
def publish_due_comment_task(self, comment_id: str) -> dict[str, str]:
    normalized_id = normalize_ulid(comment_id)
    result = execute_celery_entry(
        self,
        task_name="apps.comments.publish_due_comment",
        business_object=_business_object(normalized_id),
        idempotency_key=f"comment:{normalized_id}:visible",
        service=_publication_service,
    )
    return _task_response(result)


def _request_id(celery_task) -> str:
    try:
        return str(UUID(str(celery_task.request.id)))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid comment dispatcher request ID") from None


def _dispatch_service(business_object: str) -> str:
    del business_object
    due = due_buffered_comment_ids(
        now=SystemClock().now(),
        batch_size=settings.COMMENTS_PUBLICATION_BATCH_SIZE,
    )
    for comment_id in due:
        publish_due_comment_task.delay(comment_id)
    return f"queued:{len(due)}"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name="apps.comments.dispatch_due_comments",
)
def dispatch_due_comments(self) -> dict[str, str]:
    request_id = _request_id(self)
    result = execute_celery_entry(
        self,
        task_name="apps.comments.dispatch_due_comments",
        business_object=f"comment-publication-dispatch:{request_id}",
        idempotency_key=f"comment-publication-dispatch:{request_id}",
        service=_dispatch_service,
    )
    return _task_response(result)
