from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.public import can_upload_attachments
from apps.learning.contracts import (
    KnowledgeDocumentState,
    KnowledgeReviewRunState,
    LearningCommandError,
)
from apps.learning.models import KnowledgeDocument, KnowledgeReviewRun, LearningAppeal
from apps.learning.policies import (
    effective_learning_quota,
    locked_account_quota_state,
)

from .dispatch import ReviewDispatcher, dispatch_knowledge_review_run

_RETRYABLE_STATES = (
    KnowledgeDocumentState.REJECTED,
    KnowledgeDocumentState.REVIEW_FAILED,
)


@dataclass(frozen=True, slots=True)
class KnowledgeReviewRequest:
    document_id: UUID
    review_run_id: UUID
    document_state: str
    document_version: int


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "重新审核时间不合法。")
    return current


def create_pending_review_run(document: KnowledgeDocument) -> KnowledgeReviewRun:
    sequence = (
        document.review_runs.aggregate(maximum=Max("sequence"))["maximum"] or 0
    ) + 1
    return KnowledgeReviewRun.objects.create(
        document=document,
        sequence=sequence,
        state=KnowledgeReviewRunState.PENDING,
        input_content_sha256=document.content_sha256,
        idempotency_key=f"review:{document.id}:{sequence}",
    )


def retry_document_review_locked(
    *,
    document: KnowledgeDocument,
    dispatcher: ReviewDispatcher,
    current: datetime,
    ignore_appeal_id: UUID | None = None,
) -> KnowledgeReviewRequest:
    if not can_upload_attachments(document.owner_id):
        raise LearningCommandError(
            "learning.attachment_capability_required.v1",
            "当前账户没有知识文档审核能力。",
        )
    if document.state not in _RETRYABLE_STATES or document.media_asset_id is None:
        raise LearningCommandError(
            "learning.review_retry_conflict.v1", "知识文档当前不能重新审核。"
        )
    if (
        document.failure_purge_after is not None
        and current >= document.failure_purge_after
    ):
        raise LearningCommandError(
            "learning.review_retry_expired.v1", "知识文档的重新审核期限已结束。"
        )
    pending_appeals = LearningAppeal.objects.filter(
        document=document,
        state="PENDING",
    )
    if ignore_appeal_id is not None:
        pending_appeals = pending_appeals.exclude(pk=ignore_appeal_id)
    if pending_appeals.exists():
        raise LearningCommandError(
            "learning.appeal_pending.v1", "知识文档已有待处理申诉。"
        )
    limits = effective_learning_quota(document.owner_id)
    pending_count = KnowledgeDocument.objects.filter(
        owner_id=document.owner_id,
        state__in=(
            KnowledgeDocumentState.REVIEW_PENDING,
            KnowledgeDocumentState.REVIEWING,
        ),
    ).count()
    if pending_count >= limits.pending_reviews:
        raise LearningCommandError(
            "learning.pending_quota_exhausted.v1",
            "待审核知识文档数量已达上限。",
        )
    run = create_pending_review_run(document)
    document.state = KnowledgeDocumentState.REVIEW_PENDING
    document.last_reason_code = ""
    document.safe_status_summary = None
    document.failure_purge_after = None
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
    transaction.on_commit(
        lambda: dispatch_knowledge_review_run(run.id, dispatcher=dispatcher)
    )
    return KnowledgeReviewRequest(
        document.id,
        run.id,
        document.state,
        document.row_version,
    )


def retry_document_review(
    *,
    owner_id,
    document_id,
    expected_document_version: int,
    dispatcher: ReviewDispatcher,
    now: datetime | None = None,
) -> KnowledgeReviewRequest:
    if not isinstance(owner_id, UUID) or not isinstance(document_id, UUID):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    if not callable(dispatcher):
        raise LearningCommandError(
            "learning.review_dispatch_invalid.v1", "审核任务派发信息不合法。"
        )
    current = _current_time(now)
    with transaction.atomic():
        locked_account_quota_state(owner_id)
        try:
            document = KnowledgeDocument.objects.select_for_update().get(
                pk=document_id,
                owner_id=owner_id,
            )
        except KnowledgeDocument.DoesNotExist:
            raise LearningCommandError(
                "learning.document_not_found.v1", "知识文档不存在。"
            ) from None
        if document.row_version != expected_document_version:
            raise LearningCommandError(
                "learning.document_conflict.v1", "知识文档已被其他操作修改。"
            )
        return retry_document_review_locked(
            document=document,
            dispatcher=dispatcher,
            current=current,
        )


__all__ = [
    "KnowledgeReviewRequest",
    "create_pending_review_run",
    "retry_document_review",
    "retry_document_review_locked",
]
