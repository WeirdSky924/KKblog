from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agents.gateway import GatewayError
from apps.core.ids import normalize_ulid
from apps.operations.services.article_explanation_usage import (
    ArticleExplanationUsageResult,
    allow_article_explanation_retry,
)

from ..models import ArticleExplanationRequest
from ..queries.article_explanation import ArticleExplanationContext


class ArticleExplanationRequestError(ValueError):
    def __init__(
        self,
        message: str = "文章解释请求不可用。",
        *,
        code: str = "discovery.article_explanation_request_invalid.v1",
    ) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ArticleExplanationRequestSnapshot:
    request_id: str
    account_id: UUID
    article_id: str
    idempotency_key: str
    state: str
    task_run_id: str
    invocation_id: str
    selected_text: str
    article_title: str
    article_summary: str
    article_tags: tuple[str, ...]
    section_heading: str
    original_char_count: int
    processed_char_count: int
    was_truncated: bool
    result_markdown: str
    safe_error_code: str
    safe_error_message: str
    retryable: bool
    completed_at: datetime | None


def _snapshot(row: ArticleExplanationRequest) -> ArticleExplanationRequestSnapshot:
    tags = row.article_tags if isinstance(row.article_tags, list) else []
    return ArticleExplanationRequestSnapshot(
        request_id=row.id,
        account_id=row.account_id,
        article_id=row.article_id,
        idempotency_key=row.idempotency_key,
        state=row.state,
        task_run_id=row.task_run_id or "",
        invocation_id=row.invocation_id or "",
        selected_text=row.selected_text,
        article_title=row.article_title,
        article_summary=row.article_summary,
        article_tags=tuple(item for item in tags if isinstance(item, str)),
        section_heading=row.section_heading,
        original_char_count=row.original_char_count,
        processed_char_count=row.processed_char_count,
        was_truncated=row.was_truncated,
        result_markdown=row.result_markdown,
        safe_error_code=row.safe_error_code,
        safe_error_message=row.safe_error_message,
        retryable=row.retryable,
        completed_at=row.completed_at,
    )


def _request_id(value: object) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleExplanationRequestError("请求标识无效。") from None


def _account_id(value: object) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleExplanationRequestError("账户标识无效。") from None


def create_article_explanation_request(
    *,
    account_id,
    context: ArticleExplanationContext,
    usage: ArticleExplanationUsageResult,
    idempotency_key: str,
) -> tuple[ArticleExplanationRequestSnapshot, bool]:
    if not isinstance(context, ArticleExplanationContext):
        raise TypeError("context must be ArticleExplanationContext")
    identity = _account_id(account_id)
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ArticleExplanationRequestError("幂等标识无效。")
    if not isinstance(usage, ArticleExplanationUsageResult):
        raise TypeError("usage must be ArticleExplanationUsageResult")
    if usage.counted_toward_limit and usage.reused:
        # A reused usage row may already belong to a request.  The lookup below
        # remains the source of truth and avoids creating a second task.
        pass
    with transaction.atomic():
        existing = (
            ArticleExplanationRequest.objects.select_for_update()
            .filter(idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            if existing.account_id != identity:
                raise ArticleExplanationRequestError("幂等标识已属于其他账户。")
            return _snapshot(existing), False
        try:
            row = ArticleExplanationRequest.objects.create(
                account_id=identity,
                article_id=context.article_id,
                idempotency_key=idempotency_key,
                usage_id=usage.usage_id,
                selected_text=context.selected_text,
                article_title=context.article_title,
                article_summary=context.article_summary,
                article_tags=list(context.article_tags),
                section_heading=context.section_heading,
                original_char_count=context.original_char_count,
                processed_char_count=context.processed_char_count,
                was_truncated=context.was_truncated,
            )
        except IntegrityError:
            # Preserve the database transaction boundary while allowing the
            # caller to map uniqueness races to a safe idempotent readback.
            existing = (
                ArticleExplanationRequest.objects.select_for_update()
                .filter(idempotency_key=idempotency_key, account_id=identity)
                .first()
            )
            if existing is None:
                raise
            return _snapshot(existing), False
    return _snapshot(row), True


def article_explanation_request(
    *, account_id, request_id: str
) -> ArticleExplanationRequestSnapshot:
    identity = _account_id(account_id)
    stable_request_id = _request_id(request_id)
    try:
        row = ArticleExplanationRequest.objects.get(
            pk=stable_request_id,
            account_id=identity,
        )
    except ArticleExplanationRequest.DoesNotExist:
        raise ArticleExplanationRequestError(
            "文章解释请求不存在。",
            code="discovery.article_explanation_request_not_found.v1",
        ) from None
    return _snapshot(row)


def internal_article_explanation_request(
    *, request_id: str
) -> ArticleExplanationRequestSnapshot:
    stable_request_id = _request_id(request_id)
    try:
        row = ArticleExplanationRequest.objects.get(pk=stable_request_id)
    except ArticleExplanationRequest.DoesNotExist:
        raise ArticleExplanationRequestError(
            "文章解释请求不存在。",
            code="discovery.article_explanation_request_not_found.v1",
        ) from None
    return _snapshot(row)


def bind_article_explanation_task(*, request_id: str, task_run_id: str) -> bool:
    request_identity = _request_id(request_id)
    if not isinstance(task_run_id, str) or not task_run_id:
        raise ArticleExplanationRequestError("任务标识无效。")
    with transaction.atomic():
        row = ArticleExplanationRequest.objects.select_for_update().get(
            pk=request_identity
        )
        if row.task_run_id and row.task_run_id != task_run_id:
            raise ArticleExplanationRequestError("请求已绑定其他任务。")
        if row.state == ArticleExplanationRequest.State.CANCELLED:
            return False
        if not row.task_run_id:
            row.task_run_id = task_run_id
            row.save(update_fields=("task_run_id", "updated_at"))
    return True


def mark_article_explanation_running(*, request_id: str, task_run_id: str) -> bool:
    request_identity = _request_id(request_id)
    if not isinstance(task_run_id, str) or not task_run_id:
        raise ArticleExplanationRequestError("任务标识无效。")
    with transaction.atomic():
        row = ArticleExplanationRequest.objects.select_for_update().get(
            pk=request_identity
        )
        if row.state == ArticleExplanationRequest.State.CANCELLED:
            return False
        if row.state in {
            ArticleExplanationRequest.State.SUCCEEDED,
            ArticleExplanationRequest.State.FAILED,
        }:
            return False
        if row.task_run_id and row.task_run_id != task_run_id:
            raise ArticleExplanationRequestError("请求已绑定其他任务。")
        row.state = ArticleExplanationRequest.State.RUNNING
        row.task_run_id = task_run_id
        row.save(update_fields=("state", "task_run_id", "updated_at"))
    return True


def bind_article_explanation_invocation(*, request_id: str, invocation_id: str) -> bool:
    request_identity = _request_id(request_id)
    if not isinstance(invocation_id, str) or not invocation_id:
        raise ArticleExplanationRequestError("调用标识无效。")
    with transaction.atomic():
        row = ArticleExplanationRequest.objects.select_for_update().get(
            pk=request_identity
        )
        if row.state == ArticleExplanationRequest.State.CANCELLED:
            return False
        if row.invocation_id and row.invocation_id != invocation_id:
            raise ArticleExplanationRequestError("请求已绑定其他调用。")
        if not row.invocation_id:
            row.invocation_id = invocation_id
            row.save(update_fields=("invocation_id", "updated_at"))
    return True


def complete_article_explanation(
    *, request_id: str, result_markdown: str, completed_at: datetime | None = None
) -> bool:
    request_identity = _request_id(request_id)
    if not isinstance(result_markdown, str) or not result_markdown.strip():
        raise ArticleExplanationRequestError("解释结果为空。")
    if len(result_markdown.encode("utf-8")) > 48_000:
        raise ArticleExplanationRequestError("解释结果过大。")
    completed = completed_at or timezone.now()
    if not timezone.is_aware(completed):
        raise ArticleExplanationRequestError("完成时间无效。")
    with transaction.atomic():
        row = ArticleExplanationRequest.objects.select_for_update().get(
            pk=request_identity
        )
        if row.state == ArticleExplanationRequest.State.CANCELLED:
            return False
        if row.state == ArticleExplanationRequest.State.SUCCEEDED:
            return row.result_markdown == result_markdown
        if row.state != ArticleExplanationRequest.State.RUNNING:
            raise ArticleExplanationRequestError("请求尚未进入生成状态。")
        row.state = ArticleExplanationRequest.State.SUCCEEDED
        row.result_markdown = result_markdown
        row.safe_error_code = ""
        row.safe_error_message = ""
        row.retryable = False
        row.completed_at = completed
        row.save(
            update_fields=(
                "state",
                "result_markdown",
                "safe_error_code",
                "safe_error_message",
                "retryable",
                "completed_at",
                "updated_at",
            )
        )
    return True


def fail_article_explanation(
    *,
    request_id: str,
    error_code: str,
    message: str,
    retryable: bool,
    completed_at: datetime | None = None,
) -> bool:
    request_identity = _request_id(request_id)
    if (
        not isinstance(error_code, str)
        or not error_code
        or not isinstance(message, str)
        or not message
        or len(message) > 255
        or not isinstance(retryable, bool)
    ):
        raise ArticleExplanationRequestError("失败信息无效。")
    completed = completed_at or timezone.now()
    if not timezone.is_aware(completed):
        raise ArticleExplanationRequestError("完成时间无效。")
    with transaction.atomic():
        row = ArticleExplanationRequest.objects.select_for_update().get(
            pk=request_identity
        )
        if row.state == ArticleExplanationRequest.State.CANCELLED:
            return False
        if row.state == ArticleExplanationRequest.State.FAILED:
            return row.safe_error_code == error_code
        if row.state not in {
            ArticleExplanationRequest.State.PENDING,
            ArticleExplanationRequest.State.RUNNING,
        }:
            raise ArticleExplanationRequestError("请求已经完成。")
        row.state = ArticleExplanationRequest.State.FAILED
        row.safe_error_code = error_code[:96]
        row.safe_error_message = message
        row.retryable = retryable
        row.completed_at = completed
        row.save(
            update_fields=(
                "state",
                "safe_error_code",
                "safe_error_message",
                "retryable",
                "completed_at",
                "updated_at",
            )
        )
        usage_id = row.usage_id
    if retryable:
        from apps.operations.models import ArticleExplanationUsage

        try:
            usage = ArticleExplanationUsage.objects.only("retry_of_id").get(pk=usage_id)
        except ArticleExplanationUsage.DoesNotExist:
            raise ArticleExplanationRequestError("使用记录不存在。") from None
        allow_article_explanation_retry(
            usage_id=usage.retry_of_id or usage_id,
        )
    return True


def cancel_article_explanation(*, account_id, request_id: str) -> bool:
    identity = _account_id(account_id)
    request_identity = _request_id(request_id)
    invocation_id = ""
    with transaction.atomic():
        try:
            row = ArticleExplanationRequest.objects.select_for_update().get(
                pk=request_identity,
                account_id=identity,
            )
        except ArticleExplanationRequest.DoesNotExist:
            raise ArticleExplanationRequestError(
                "文章解释请求不存在。",
                code="discovery.article_explanation_request_not_found.v1",
            ) from None
        if row.state in {
            ArticleExplanationRequest.State.SUCCEEDED,
            ArticleExplanationRequest.State.FAILED,
            ArticleExplanationRequest.State.CANCELLED,
        }:
            return row.state == ArticleExplanationRequest.State.CANCELLED
        row.state = ArticleExplanationRequest.State.CANCELLED
        row.completed_at = timezone.now()
        row.safe_error_code = ""
        row.safe_error_message = ""
        row.retryable = False
        row.save(
            update_fields=(
                "state",
                "completed_at",
                "safe_error_code",
                "safe_error_message",
                "retryable",
                "updated_at",
            )
        )
        invocation_id = row.invocation_id
    if invocation_id:
        from apps.agents.services.runtime import cancel_invocation

        cancel_invocation(invocation_id=invocation_id, completed_at=timezone.now())
    return True


def retry_article_explanation(
    *,
    account_id,
    request_id: str,
    context: ArticleExplanationContext,
    usage,
    idempotency_key: str,
) -> tuple[ArticleExplanationRequestSnapshot, bool]:
    identity = _account_id(account_id)
    original = article_explanation_request(
        account_id=identity,
        request_id=request_id,
    )
    if (
        original.state != ArticleExplanationRequest.State.FAILED
        or not original.retryable
    ):
        raise ArticleExplanationRequestError(
            "当前解释请求不允许重试。",
            code="discovery.article_explanation_retry_unavailable.v1",
        )
    return create_article_explanation_request(
        account_id=identity,
        context=context,
        usage=usage,
        idempotency_key=idempotency_key,
    )


def safe_explanation_markdown(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArticleExplanationRequestError("解释结果为空。")
    if len(value.encode("utf-8")) > 48_000 or "\x00" in value:
        raise ArticleExplanationRequestError("解释结果不安全。")
    from apps.content.rendering import sanitized_article_readable_markdown
    from apps.media.rendering import TrustedEmbedPolicy, render_markdown

    try:
        rendered = render_markdown(
            value,
            embed_policy=TrustedEmbedPolicy(enabled_sources=()),
        )
        safe = sanitized_article_readable_markdown(rendered.html)
    except Exception:
        raise ArticleExplanationRequestError("解释结果无法安全显示。") from None
    if not safe.strip():
        raise ArticleExplanationRequestError("解释结果为空。")
    return safe[:48_000]


def safe_explanation_html(value: object) -> str:
    markdown = safe_explanation_markdown(value)
    from apps.media.rendering import TrustedEmbedPolicy, render_markdown

    try:
        return render_markdown(
            markdown,
            embed_policy=TrustedEmbedPolicy(enabled_sources=()),
        ).html
    except Exception:
        raise ArticleExplanationRequestError("解释结果无法安全显示。") from None


def gateway_failure(error: GatewayError) -> tuple[str, str, bool]:
    retryable = bool(error.retryable)
    message = (
        "上游解释服务暂时失败，请稍后重试。"
        if retryable
        else "解释服务暂时无法完成请求。"
    )
    return error.code[:96], message, retryable


__all__ = [
    "ArticleExplanationRequestError",
    "ArticleExplanationRequestSnapshot",
    "article_explanation_request",
    "bind_article_explanation_invocation",
    "bind_article_explanation_task",
    "cancel_article_explanation",
    "complete_article_explanation",
    "create_article_explanation_request",
    "fail_article_explanation",
    "gateway_failure",
    "internal_article_explanation_request",
    "mark_article_explanation_running",
    "retry_article_explanation",
    "safe_explanation_markdown",
    "safe_explanation_html",
]
