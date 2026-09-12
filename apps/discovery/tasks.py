from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.agents.gateway import GatewayError, build_agent_gateway
from apps.agents.public import create_agent_invocation
from apps.agents.services.runtime import cancel_invocation
from apps.core.ids import normalize_ulid
from apps.operations.public import (
    TaskCancelled,
    TaskFinalFailed,
    current_task_run_id,
    execute_celery_entry,
)

from .services.article_explanation import (
    ArticleExplanationRequestError,
    bind_article_explanation_invocation,
    complete_article_explanation,
    fail_article_explanation,
    gateway_failure,
    internal_article_explanation_request,
    mark_article_explanation_running,
    safe_explanation_markdown,
)

ARTICLE_EXPLANATION_TASK_NAME = "apps.discovery.article_explanation"
ARTICLE_EXPLANATION_PROFILE_KEY = "article-selection-explanation"
_BUSINESS_PREFIX = "article-explanation:"


def dispatch_article_explanation(request_id: str) -> None:
    article_explanation_task.delay(normalize_ulid(request_id))


def _request_id(business_object: str) -> str:
    if not isinstance(business_object, str) or not business_object.startswith(
        _BUSINESS_PREFIX
    ):
        raise ValueError("文章解释任务对象无效。")
    return normalize_ulid(business_object[len(_BUSINESS_PREFIX) :])


def _estimate_input_tokens(request) -> int:
    characters = len(request.selected_text)
    metadata = len(
        "\n".join(
            (
                request.article_title,
                request.article_summary,
                "、".join(request.article_tags),
                request.section_heading,
            )
        )
    )
    return max(1, (characters + metadata + 3) // 4)


def _cancelled(request_id: str) -> bool:
    return (
        internal_article_explanation_request(request_id=request_id).state == "CANCELLED"
    )


def _execute_article_explanation(business_object: str) -> str:
    request_id = _request_id(business_object)
    task_run_id = current_task_run_id()
    if task_run_id is None:
        raise TaskFinalFailed(
            error_code="discovery.article_explanation_task_invalid.v1"
        )
    request = internal_article_explanation_request(request_id=request_id)
    if request.state == "CANCELLED":
        raise TaskCancelled(result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled")
    if request.state == "SUCCEEDED":
        return f"{_BUSINESS_PREFIX}{request_id}:succeeded"
    if request.state == "FAILED":
        raise TaskFinalFailed(
            error_code=request.safe_error_code
            or "discovery.article_explanation_already_failed.v1"
        )
    if not mark_article_explanation_running(
        request_id=request_id,
        task_run_id=task_run_id,
    ):
        raise TaskCancelled(result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled")
    request = internal_article_explanation_request(request_id=request_id)
    if request.invocation_id:
        invocation_id = request.invocation_id
    else:
        try:
            invocation = create_agent_invocation(
                profile_key=ARTICLE_EXPLANATION_PROFILE_KEY,
                caller_type="article_explanation",
                caller_id=request.request_id,
                idempotency_key=f"{_BUSINESS_PREFIX}{request.request_id}",
                estimated_input_tokens=_estimate_input_tokens(request),
                task_run_id=task_run_id,
            )
        except Exception as error:
            fail_article_explanation(
                request_id=request_id,
                error_code=(
                    getattr(error, "code", "")
                    or "discovery.article_explanation_configuration_unavailable.v1"
                ),
                message="解释服务当前不可用，请稍后再试。",
                retryable=False,
            )
            raise TaskFinalFailed(
                error_code="discovery.article_explanation_configuration_unavailable.v1"
            ) from None
        invocation_id = invocation.id
        if not bind_article_explanation_invocation(
            request_id=request_id,
            invocation_id=invocation_id,
        ):
            cancel_invocation(invocation_id=invocation_id, completed_at=timezone.now())
            raise TaskCancelled(result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled")
    if _cancelled(request_id):
        cancel_invocation(invocation_id=invocation_id, completed_at=timezone.now())
        raise TaskCancelled(result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled")
    try:
        result = build_agent_gateway().execute(
            invocation_id=invocation_id,
            input_blocks=(request.selected_text,),
            prompt_variables={
                "article_title": request.article_title,
                "article_summary": request.article_summary or "无",
                "article_tags": "、".join(request.article_tags) or "无",
                "section_heading": request.section_heading or "无",
                "selected_text": request.selected_text,
            },
            cancel_check=lambda: _cancelled(request_id),
            lease_seconds=3_600,
        )
        safe_result = safe_explanation_markdown(
            result.value.get("explanation_markdown", "")
        )
    except GatewayError as error:
        if _cancelled(request_id):
            raise TaskCancelled(
                result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled"
            ) from None
        code, message, retryable = gateway_failure(error)
        fail_article_explanation(
            request_id=request_id,
            error_code=code,
            message=message,
            retryable=retryable,
        )
        raise TaskFinalFailed(error_code=code) from None
    except TaskCancelled:
        raise
    except ArticleExplanationRequestError as error:
        fail_article_explanation(
            request_id=request_id,
            error_code=error.code,
            message=str(error),
            retryable=False,
        )
        raise TaskFinalFailed(error_code=error.code) from None
    except Exception:
        if _cancelled(request_id):
            raise TaskCancelled(
                result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled"
            ) from None
        code = "discovery.article_explanation_execution_failed.v1"
        fail_article_explanation(
            request_id=request_id,
            error_code=code,
            message="解释服务暂时失败，请稍后重试。",
            retryable=True,
        )
        raise TaskFinalFailed(error_code=code) from None
    if not complete_article_explanation(
        request_id=request_id,
        result_markdown=safe_result,
    ):
        raise TaskCancelled(result_ref=f"{_BUSINESS_PREFIX}{request_id}:cancelled")
    return f"{_BUSINESS_PREFIX}{request_id}:succeeded"


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=None,
    name=ARTICLE_EXPLANATION_TASK_NAME,
)
def article_explanation_task(self, request_id: str) -> dict[str, str]:
    identity = normalize_ulid(request_id)
    result = execute_celery_entry(
        self,
        task_name=ARTICLE_EXPLANATION_TASK_NAME,
        business_object=f"{_BUSINESS_PREFIX}{identity}",
        idempotency_key=f"{_BUSINESS_PREFIX}{identity}",
        service=_execute_article_explanation,
        lease_seconds=7_200,
    )
    return {"status": result.outcome.value, "result_ref": result.result_ref}


__all__ = [
    "ARTICLE_EXPLANATION_TASK_NAME",
    "article_explanation_task",
    "dispatch_article_explanation",
]
