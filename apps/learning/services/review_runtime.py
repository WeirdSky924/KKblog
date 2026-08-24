import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import can_upload_attachments
from apps.agents.public import (
    AgentCommandError,
    AgentGateway,
    GatewayError,
    create_agent_invocation,
    invoke_structured,
)
from apps.core.ids import normalize_ulid
from apps.learning.contracts import (
    KnowledgeDocumentState,
    KnowledgeReviewOutcome,
    KnowledgeReviewRunState,
    LearningCommandError,
    LearningModelRunKind,
)
from apps.learning.models import (
    KnowledgeDocument,
    KnowledgeReviewRun,
    LearningModelRunReservation,
)
from apps.media.public import MediaStorage
from apps.operations.public import RetryableTaskError, TaskCancelled, TaskFinalFailed

from ..review_schema import KNOWLEDGE_REVIEW_PROFILE_KEY
from .document_inputs import knowledge_document_input
from .quotas import release_learning_model_run, reserve_learning_model_run
from .reviews import complete_knowledge_review

_SAFE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class KnowledgeReviewExecutionResult:
    document_id: UUID
    review_run_id: UUID
    document_state: str
    invocation_id: str | None


@dataclass(frozen=True, slots=True)
class _ReviewClaim:
    document_id: UUID
    owner_id: UUID
    document_version: int
    attempt: int


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError(
            "learning.time_invalid.v1", "知识文档审核时间不合法。"
        )
    return current


def _review_identity(value) -> UUID:
    if not isinstance(value, UUID):
        raise LearningCommandError(
            "learning.review_not_found.v1", "知识文档审核不存在。"
        )
    return value


def _task_run_identity(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.review_task_invalid.v1", "审核任务运行标识不合法。"
        ) from None


def _review_source(
    *, review_run_id: UUID, storage: MediaStorage | None
) -> tuple[KnowledgeReviewRun, tuple[str, ...], int]:
    try:
        run = KnowledgeReviewRun.objects.select_related("document").get(
            pk=review_run_id
        )
    except KnowledgeReviewRun.DoesNotExist:
        raise LearningCommandError(
            "learning.review_not_found.v1", "知识文档审核不存在。"
        ) from None
    document = run.document
    if document.state == KnowledgeDocumentState.DELETE_PENDING:
        raise TaskCancelled(result_ref=f"knowledge-review:{run.id}:deleted")
    if document.media_asset_id is None:
        raise TaskCancelled(result_ref=f"knowledge-review:{run.id}:content-purged")
    prepared = knowledge_document_input(document, storage=storage)
    return run, prepared.blocks, prepared.estimated_tokens


def _claim_review_attempt(
    *,
    review_run_id: UUID,
    task_run_id: str,
    chunk_count: int,
    estimated_input_tokens: int,
    now: datetime,
) -> _ReviewClaim:
    with transaction.atomic():
        try:
            run = KnowledgeReviewRun.objects.select_for_update().get(pk=review_run_id)
            document = KnowledgeDocument.objects.select_for_update().get(
                pk=run.document_id
            )
        except (KnowledgeReviewRun.DoesNotExist, KnowledgeDocument.DoesNotExist):
            raise LearningCommandError(
                "learning.review_not_found.v1", "知识文档审核不存在。"
            ) from None
        if document.state == KnowledgeDocumentState.DELETE_PENDING:
            raise TaskCancelled(result_ref=f"knowledge-review:{run.id}:deleted")
        if not can_upload_attachments(document.owner_id):
            raise RetryableTaskError("learning.attachment_capability_required.v1")
        if run.attempt_count >= 3:
            raise LearningCommandError(
                "learning.review_conflict.v1", "知识文档审核已达到尝试上限。"
            )
        if run.state == KnowledgeReviewRunState.PENDING:
            if document.state != KnowledgeDocumentState.REVIEW_PENDING:
                raise LearningCommandError(
                    "learning.review_conflict.v1", "知识文档审核状态冲突。"
                )
            document.state = KnowledgeDocumentState.REVIEWING
            document.row_version += 1
            document.save(update_fields=("state", "row_version", "updated_at"))
            run.state = KnowledgeReviewRunState.RUNNING
            run.started_at = now
            run.task_run_id = task_run_id
        elif (
            run.state != KnowledgeReviewRunState.RUNNING
            or document.state != KnowledgeDocumentState.REVIEWING
            or run.task_run_id != task_run_id
        ):
            raise LearningCommandError(
                "learning.review_conflict.v1", "知识文档审核状态冲突。"
            )
        run.attempt_count += 1
        run.chunk_count = chunk_count
        run.estimated_input_tokens = estimated_input_tokens
        run.last_error_code = ""
        run.row_version += 1
        run.save()
    return _ReviewClaim(
        document_id=document.id,
        owner_id=document.owner_id,
        document_version=document.row_version,
        attempt=run.attempt_count,
    )


def _record_runtime_ids(
    *,
    review_run_id: UUID,
    task_run_id: str,
    invocation_id: str,
    reservation_id: UUID,
) -> None:
    updated = KnowledgeReviewRun.objects.filter(
        pk=review_run_id,
        state=KnowledgeReviewRunState.RUNNING,
        task_run_id=task_run_id,
    ).update(
        latest_invocation_id=invocation_id,
        latest_learning_reservation_id=reservation_id,
        last_error_code="",
    )
    if updated != 1:
        raise TaskCancelled(result_ref=f"knowledge-review:{review_run_id}:cancelled")


def _record_retry_error(
    *, review_run_id: UUID, task_run_id: str, error_code: str
) -> None:
    if _SAFE_ERROR_CODE.fullmatch(error_code):
        KnowledgeReviewRun.objects.filter(
            pk=review_run_id,
            state=KnowledgeReviewRunState.RUNNING,
            task_run_id=task_run_id,
        ).update(last_error_code=error_code)


def execute_knowledge_review(
    *,
    review_run_id,
    task_run_id: str,
    gateway: AgentGateway,
    renew_lease,
    storage: MediaStorage | None = None,
    now: datetime | None = None,
) -> KnowledgeReviewExecutionResult:
    identity = _review_identity(review_run_id)
    stable_task_run_id = _task_run_identity(task_run_id)
    current = _current_time(now)
    if not isinstance(gateway, AgentGateway) or not callable(renew_lease):
        raise LearningCommandError(
            "learning.review_runtime_invalid.v1", "知识文档审核运行器不合法。"
        )
    try:
        _, blocks, estimated_tokens = _review_source(
            review_run_id=identity,
            storage=storage,
        )
    except LearningCommandError as error:
        if error.code not in {
            "learning.document_link_unsafe.v1",
            "learning.document_structure_invalid.v1",
        }:
            raise
        run = KnowledgeReviewRun.objects.select_related("document").get(pk=identity)
        claim = _claim_review_attempt(
            review_run_id=identity,
            task_run_id=stable_task_run_id,
            chunk_count=1,
            estimated_input_tokens=max(1, run.document.estimated_tokens or 1),
            now=current,
        )
        completed = complete_knowledge_review(
            document_id=claim.document_id,
            review_run_id=identity,
            expected_document_version=claim.document_version,
            outcome=KnowledgeReviewOutcome.REJECTED,
            safe_reason_code=error.code.removesuffix(".v1").replace(".", "_"),
            safe_summary="知识文档未通过确定性安全校验。",
            risk_categories=("deterministic_gate",),
            now=current,
        )
        return KnowledgeReviewExecutionResult(
            claim.document_id,
            identity,
            completed.document_state,
            None,
        )

    claim = _claim_review_attempt(
        review_run_id=identity,
        task_run_id=stable_task_run_id,
        chunk_count=len(blocks),
        estimated_input_tokens=estimated_tokens,
        now=current,
    )
    renew_lease()
    reservation = None
    try:
        reservation = reserve_learning_model_run(
            account_id=claim.owner_id,
            kind=LearningModelRunKind.REVIEW,
            owner_ref=f"{identity}:{claim.attempt}",
            idempotency_key=f"review-runtime:{identity}:{claim.attempt}",
            lease_expires_at=current + timedelta(hours=1),
            now=current,
        )
        invocation = create_agent_invocation(
            profile_key=KNOWLEDGE_REVIEW_PROFILE_KEY,
            caller_type="knowledge_review",
            caller_id=f"{identity}:{claim.attempt}",
            idempotency_key=f"review:{identity}:{claim.attempt}",
            estimated_input_tokens=estimated_tokens,
            task_run_id=stable_task_run_id,
        )
        _record_runtime_ids(
            review_run_id=identity,
            task_run_id=stable_task_run_id,
            invocation_id=invocation.id,
            reservation_id=reservation.reservation_id,
        )
        result = invoke_structured(
            gateway=gateway,
            invocation_id=invocation.id,
            input_blocks=blocks,
            prompt_variables={"block_count": str(len(blocks))},
            now=current,
            lease_seconds=3_600,
        )
        renew_lease()
    except (AgentCommandError, GatewayError, LearningCommandError) as error:
        code = error.code
        _record_retry_error(
            review_run_id=identity,
            task_run_id=stable_task_run_id,
            error_code=code,
        )
        if reservation is not None:
            release_learning_model_run(reservation_id=reservation.reservation_id)
        if isinstance(error, GatewayError) and not error.retryable:
            raise TaskFinalFailed(error_code=code) from None
        raise RetryableTaskError(code) from None
    except Exception:
        if reservation is not None:
            release_learning_model_run(reservation_id=reservation.reservation_id)
        raise

    release_learning_model_run(reservation_id=reservation.reservation_id)
    validated = result.validated_output
    value = validated.value
    try:
        completed = complete_knowledge_review(
            document_id=claim.document_id,
            review_run_id=identity,
            expected_document_version=claim.document_version,
            outcome=KnowledgeReviewOutcome(value["verdict"]),
            safe_reason_code=value["reason_code"],
            safe_summary=value["summary"],
            risk_categories=tuple(value["risk_categories"]),
            now=current,
        )
    except LearningCommandError:
        state = KnowledgeDocument.objects.values_list("state", flat=True).get(
            pk=claim.document_id
        )
        if state == KnowledgeDocumentState.DELETE_PENDING:
            raise TaskCancelled(
                result_ref=f"knowledge-review:{identity}:deleted"
            ) from None
        raise
    return KnowledgeReviewExecutionResult(
        claim.document_id,
        identity,
        completed.document_state,
        result.invocation_id,
    )


def mark_knowledge_review_final_failed(
    *,
    review_run_id,
    safe_error_code: str,
    completed_at: datetime,
) -> KnowledgeReviewExecutionResult:
    identity = _review_identity(review_run_id)
    current = _current_time(completed_at)
    if (
        not isinstance(safe_error_code, str)
        or _SAFE_ERROR_CODE.fullmatch(safe_error_code) is None
    ):
        raise LearningCommandError(
            "learning.review_result_invalid.v1", "审核失败结果不合法。"
        )
    try:
        run = KnowledgeReviewRun.objects.select_related("document").get(pk=identity)
    except KnowledgeReviewRun.DoesNotExist:
        raise LearningCommandError(
            "learning.review_not_found.v1", "知识文档审核不存在。"
        ) from None
    document = run.document
    if document.state == KnowledgeDocumentState.REVIEW_FAILED:
        return KnowledgeReviewExecutionResult(document.id, run.id, document.state, None)
    if document.state == KnowledgeDocumentState.DELETE_PENDING:
        return KnowledgeReviewExecutionResult(document.id, run.id, document.state, None)
    active_reservation_ids = tuple(
        LearningModelRunReservation.objects.filter(
            account_id=document.owner_id,
            owner_ref__startswith=f"{run.id}:",
            status="ACTIVE",
        ).values_list("id", flat=True)
    )
    for reservation_id in active_reservation_ids:
        release_learning_model_run(reservation_id=reservation_id)
    completed = complete_knowledge_review(
        document_id=document.id,
        review_run_id=run.id,
        expected_document_version=document.row_version,
        outcome=KnowledgeReviewOutcome.FAILED,
        safe_reason_code=safe_error_code,
        safe_summary="审核任务在三次尝试后仍未成功。",
        risk_categories=(),
        now=current,
    )
    return KnowledgeReviewExecutionResult(
        document.id,
        run.id,
        completed.document_state,
        run.latest_invocation_id,
    )


__all__ = [
    "KnowledgeReviewExecutionResult",
    "execute_knowledge_review",
    "mark_knowledge_review_final_failed",
]
