import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import can_upload_attachments
from apps.core.events import enqueue_event
from apps.learning.contracts import (
    KnowledgeDocumentState,
    KnowledgeReviewOutcome,
    KnowledgeReviewRunState,
    LearningCommandError,
)
from apps.learning.models import KnowledgeDocument, KnowledgeReviewRun

from ..events import REVIEW_APPROVED, REVIEW_FAILED, REVIEW_REJECTED

_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_RISK_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_OUTCOME_STATES = {
    KnowledgeReviewOutcome.APPROVED: (
        KnowledgeDocumentState.APPROVED,
        KnowledgeReviewRunState.APPROVED,
    ),
    KnowledgeReviewOutcome.REJECTED: (
        KnowledgeDocumentState.REJECTED,
        KnowledgeReviewRunState.REJECTED,
    ),
    KnowledgeReviewOutcome.FAILED: (
        KnowledgeDocumentState.REVIEW_FAILED,
        KnowledgeReviewRunState.FAILED,
    ),
}
_OUTCOME_EVENTS = {
    KnowledgeReviewOutcome.APPROVED: REVIEW_APPROVED,
    KnowledgeReviewOutcome.REJECTED: REVIEW_REJECTED,
    KnowledgeReviewOutcome.FAILED: REVIEW_FAILED,
}


@dataclass(frozen=True, slots=True)
class KnowledgeReviewTransition:
    document_id: UUID
    review_run_id: UUID
    document_state: str
    run_state: str
    document_version: int


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "审核时间不合法。")
    return current


def _identities(document_id, review_run_id) -> tuple[UUID, UUID]:
    if not isinstance(document_id, UUID) or not isinstance(review_run_id, UUID):
        raise LearningCommandError(
            "learning.review_not_found.v1", "知识文档审核不存在。"
        )
    return document_id, review_run_id


def claim_knowledge_review(
    *,
    document_id,
    review_run_id,
    expected_document_version: int,
    now: datetime | None = None,
) -> KnowledgeReviewTransition:
    document_identity, run_identity = _identities(document_id, review_run_id)
    current = _current_time(now)
    with transaction.atomic():
        try:
            document = KnowledgeDocument.objects.select_for_update().get(
                pk=document_identity
            )
            run = KnowledgeReviewRun.objects.select_for_update().get(
                pk=run_identity,
                document=document,
            )
        except (KnowledgeDocument.DoesNotExist, KnowledgeReviewRun.DoesNotExist):
            raise LearningCommandError(
                "learning.review_not_found.v1", "知识文档审核不存在。"
            ) from None
        if (
            document.row_version != expected_document_version
            or document.state != KnowledgeDocumentState.REVIEW_PENDING
            or run.state != KnowledgeReviewRunState.PENDING
        ):
            raise LearningCommandError(
                "learning.review_conflict.v1", "知识文档审核状态冲突。"
            )
        if not can_upload_attachments(document.owner_id):
            raise LearningCommandError(
                "learning.attachment_capability_required.v1",
                "当前账户没有知识文档审核能力。",
            )
        document.state = KnowledgeDocumentState.REVIEWING
        document.row_version += 1
        document.save(update_fields=("state", "row_version", "updated_at"))
        run.state = KnowledgeReviewRunState.RUNNING
        run.started_at = current
        run.row_version += 1
        run.save(update_fields=("state", "started_at", "row_version", "updated_at"))
    return KnowledgeReviewTransition(
        document_id=document.id,
        review_run_id=run.id,
        document_state=document.state,
        run_state=run.state,
        document_version=document.row_version,
    )


def complete_knowledge_review(
    *,
    document_id,
    review_run_id,
    expected_document_version: int,
    outcome,
    safe_reason_code: str,
    safe_summary: str,
    risk_categories: tuple[str, ...],
    now: datetime | None = None,
) -> KnowledgeReviewTransition:
    document_identity, run_identity = _identities(document_id, review_run_id)
    current = _current_time(now)
    try:
        normalized_outcome = KnowledgeReviewOutcome(outcome)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.review_result_invalid.v1", "审核结果不合法。"
        ) from None
    if (
        not isinstance(safe_reason_code, str)
        or _SAFE_CODE.fullmatch(safe_reason_code) is None
        or not isinstance(safe_summary, str)
        or not 1 <= len(safe_summary.strip()) <= 500
        or not isinstance(risk_categories, tuple)
        or len(risk_categories) > 16
        or any(
            not isinstance(item, str) or _RISK_CODE.fullmatch(item) is None
            for item in risk_categories
        )
    ):
        raise LearningCommandError(
            "learning.review_result_invalid.v1", "审核结果不合法。"
        )
    document_state, run_state = _OUTCOME_STATES[normalized_outcome]
    failure_purge_after = (
        current + timedelta(days=30)
        if normalized_outcome
        in {KnowledgeReviewOutcome.REJECTED, KnowledgeReviewOutcome.FAILED}
        else None
    )
    with transaction.atomic():
        try:
            document = KnowledgeDocument.objects.select_for_update().get(
                pk=document_identity
            )
            run = KnowledgeReviewRun.objects.select_for_update().get(
                pk=run_identity,
                document=document,
            )
        except (KnowledgeDocument.DoesNotExist, KnowledgeReviewRun.DoesNotExist):
            raise LearningCommandError(
                "learning.review_not_found.v1", "知识文档审核不存在。"
            ) from None
        if (
            document.row_version != expected_document_version
            or document.state != KnowledgeDocumentState.REVIEWING
            or run.state != KnowledgeReviewRunState.RUNNING
        ):
            raise LearningCommandError(
                "learning.review_conflict.v1", "知识文档审核状态冲突。"
            )
        document.state = document_state
        document.last_reason_code = safe_reason_code
        document.safe_status_summary = safe_summary.strip()
        document.failure_purge_after = failure_purge_after
        document.row_version += 1
        document.save(
            update_fields=(
                "state",
                "last_reason_code",
                "safe_status_summary",
                "failure_purge_after",
                "row_version",
                "updated_at",
            )
        )
        run.state = run_state
        run.safe_reason_code = safe_reason_code
        run.safe_summary = safe_summary.strip()
        run.risk_categories = list(dict.fromkeys(risk_categories))
        run.completed_at = current
        run.failure_purge_after = failure_purge_after
        run.row_version += 1
        run.save(
            update_fields=(
                "state",
                "safe_reason_code",
                "safe_summary",
                "risk_categories",
                "completed_at",
                "failure_purge_after",
                "row_version",
                "updated_at",
            )
        )
        enqueue_event(
            _OUTCOME_EVENTS[normalized_outcome],
            aggregate_type="knowledge_document",
            aggregate_id=str(document.id),
            payload={"recipient_id": str(document.owner_id)},
        )
    return KnowledgeReviewTransition(
        document_id=document.id,
        review_run_id=run.id,
        document_state=document.state,
        run_state=run.state,
        document_version=document.row_version,
    )
