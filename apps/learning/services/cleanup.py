from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.agents.services.usage import recover_expired_token_reservations
from apps.learning.contracts import (
    KnowledgeDocumentState,
    LearningCommandError,
    LearningModelRunStatus,
    QuestionBankVisibility,
)
from apps.learning.models import (
    KnowledgeDocument,
    KnowledgeDocumentAccess,
    KnowledgeReviewRun,
    LearningAppeal,
    LearningDailyUsage,
    LearningModelRunReservation,
    Question,
    QuestionBank,
    QuestionBankKnowledgePoint,
    QuestionBankRevision,
    QuestionBankSeries,
    QuestionBankTagAssignment,
    QuizAttempt,
    WrongQuestion,
)
from apps.media.public import MediaTargetType, release_target_assets
from apps.media.storage import FilesystemMediaStorage, MediaStorage

from .lifecycle import purge_due_knowledge_document, purge_failed_knowledge_document
from .records import purge_due_quiz_record


@dataclass(frozen=True, slots=True)
class LearningCleanupBatchResult:
    documents_deleted: int
    documents_content_purged: int
    banks_deleted: int
    quiz_records_deleted: int
    learning_reservations_expired: int
    agent_reservations_released: int
    agent_reservations_conservative: int


@dataclass(frozen=True, slots=True)
class QuestionBankCleanupResult:
    bank_id: UUID
    outcome: str


def _now(value: datetime | None) -> datetime:
    current = value or timezone.now()
    if not timezone.is_aware(current):
        raise LearningCommandError(
            "learning.cleanup_time_invalid.v1", "清理时间不合法。"
        )
    return current


def purge_due_question_bank(
    *, bank_id, now: datetime | None = None
) -> QuestionBankCleanupResult:
    current = _now(now)
    with transaction.atomic():
        try:
            bank = QuestionBank.objects.select_for_update().get(pk=bank_id)
        except (QuestionBank.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.bank_not_found.v1", "题库不存在。"
            ) from None
        if bank.visibility == QuestionBankVisibility.DELETED:
            return QuestionBankCleanupResult(bank.id, "already_deleted")
        if (
            bank.visibility != QuestionBankVisibility.DELETE_PENDING
            or bank.purge_after is None
            or current < bank.purge_after
            or LearningAppeal.objects.filter(
                question_bank=bank, state="PENDING"
            ).exists()
        ):
            return QuestionBankCleanupResult(bank.id, "not_due")
        revision_ids = tuple(
            QuestionBankRevision.objects.filter(bank=bank).values_list("id", flat=True)
        )
        bank.current_revision = None
        bank.visibility = QuestionBankVisibility.DELETED
        bank.deleted_at = current
        bank.pre_delete_visibility = None
        bank.deletion_requested_at = None
        bank.deletion_actor = ""
        bank.purge_after = None
        bank.save(
            update_fields=(
                "current_revision",
                "visibility",
                "deleted_at",
                "pre_delete_visibility",
                "deletion_requested_at",
                "deletion_actor",
                "purge_after",
                "updated_at",
            )
        )
        Question.objects.filter(revision_id__in=revision_ids).delete()
        QuestionBankRevision.objects.filter(id__in=revision_ids).delete()
        LearningAppeal.objects.filter(question_bank=bank).delete()
        bank_id_value = bank.id
        bank.delete()
    return QuestionBankCleanupResult(bank_id_value, "deleted")


def expire_learning_model_run_reservations(
    *, now: datetime | None = None, batch_size: int = 100
) -> int:
    current = _now(now)
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1_000
    ):
        raise LearningCommandError(
            "learning.cleanup_batch_invalid.v1", "清理批次不合法。"
        )
    with transaction.atomic():
        rows = list(
            LearningModelRunReservation.objects.select_for_update(skip_locked=True)
            .filter(status=LearningModelRunStatus.ACTIVE, lease_expires_at__lte=current)
            .order_by("lease_expires_at", "id")[:batch_size]
        )
        for row in rows:
            row.status = LearningModelRunStatus.EXPIRED
            row.released_at = current
            row.save(update_fields=("status", "released_at", "updated_at"))
    return len(rows)


def cleanup_learning_expired(
    *,
    now: datetime | None = None,
    batch_size: int = 50,
    storage: MediaStorage | None = None,
) -> LearningCleanupBatchResult:
    current = _now(now)
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 500
    ):
        raise LearningCommandError(
            "learning.cleanup_batch_invalid.v1", "清理批次不合法。"
        )
    active_storage = storage or FilesystemMediaStorage(settings.MEDIA_ROOT)
    deleted = 0
    content_purged = 0
    banks_deleted = 0
    records_deleted = 0
    document_ids = tuple(
        KnowledgeDocument.objects.filter(
            state=KnowledgeDocumentState.DELETE_PENDING,
            purge_after__lte=current,
        )
        .order_by("purge_after", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    for document_id in document_ids:
        result = purge_due_knowledge_document(
            document_id=document_id, now=current, storage=active_storage
        )
        if result.outcome.value == "DELETED":
            deleted += 1
    failed_ids = tuple(
        KnowledgeDocument.objects.filter(
            state__in=(
                KnowledgeDocumentState.REJECTED,
                KnowledgeDocumentState.REVIEW_FAILED,
            ),
            failure_purge_after__lte=current,
        )
        .order_by("failure_purge_after", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    for document_id in failed_ids:
        result = purge_failed_knowledge_document(
            document_id=document_id, now=current, storage=active_storage
        )
        if result.outcome.value == "CONTENT_PURGED":
            content_purged += 1
    bank_ids = tuple(
        QuestionBank.objects.filter(
            visibility=QuestionBankVisibility.DELETE_PENDING,
            purge_after__lte=current,
        )
        .order_by("purge_after", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    for bank_id in bank_ids:
        if purge_due_question_bank(bank_id=bank_id, now=current).outcome == "deleted":
            banks_deleted += 1
    record_ids = tuple(
        QuizAttempt.objects.filter(status="DELETE_PENDING", purge_after__lte=current)
        .order_by("purge_after", "id")
        .values_list("id", flat=True)[:batch_size]
    )
    for attempt_id in record_ids:
        if purge_due_quiz_record(attempt_id=attempt_id, now=current).changed:
            records_deleted += 1
    expired_learning = expire_learning_model_run_reservations(
        now=current, batch_size=batch_size
    )
    recovered = recover_expired_token_reservations(now=current, batch_size=batch_size)
    return LearningCleanupBatchResult(
        deleted,
        content_purged,
        banks_deleted,
        records_deleted,
        expired_learning,
        recovered.released_count,
        recovered.conservative_count,
    )


def purge_account_learning_data(*, account_id: UUID) -> dict[str, int]:
    if not isinstance(account_id, UUID):
        raise ValueError("Invalid learning account ID")
    with transaction.atomic():
        document_ids = tuple(
            KnowledgeDocument.objects.filter(owner_id=account_id).values_list(
                "id", flat=True
            )
        )
        series_ids = tuple(
            QuestionBankSeries.objects.filter(owner_id=account_id).values_list(
                "id", flat=True
            )
        )
        bank_ids = tuple(
            QuestionBank.objects.filter(series_id__in=series_ids).values_list(
                "id", flat=True
            )
        )
        # Preserve other users' historical explanations while removing the deleted author's identity.
        QuizAttempt.objects.filter(owner_id_snapshot=account_id).exclude(
            account_id=account_id
        ).update(owner_id_snapshot=None, owner_display_name="已注销用户")
        WrongQuestion.objects.filter(bank_id__in=bank_ids).update(
            bank_id=None, question_id=None, owner_display_name="已注销用户"
        )
        QuizAttempt.objects.filter(account_id=account_id).delete()
        WrongQuestion.objects.filter(account_id=account_id).delete()
        LearningDailyUsage.objects.filter(account_id=account_id).delete()
        LearningModelRunReservation.objects.filter(account_id=account_id).delete()
        if document_ids:
            release_target_assets(
                target_type=MediaTargetType.LEARNING_DOCUMENT,
                target_ids=tuple(str(item) for item in document_ids),
            )
            LearningAppeal.objects.filter(document_id__in=document_ids).delete()
            KnowledgeDocumentAccess.objects.filter(
                document_id__in=document_ids
            ).delete()
            KnowledgeReviewRun.objects.filter(document_id__in=document_ids).delete()
        if bank_ids:
            LearningAppeal.objects.filter(question_bank_id__in=bank_ids).delete()
            QuestionBankTagAssignment.objects.filter(series_id__in=series_ids).delete()
            revision_ids = tuple(
                QuestionBankRevision.objects.filter(bank_id__in=bank_ids).values_list(
                    "id", flat=True
                )
            )
            QuestionBank.objects.filter(id__in=bank_ids).update(
                current_revision=None,
                visibility=QuestionBankVisibility.DELETED,
                deleted_at=timezone.now(),
                pre_delete_visibility=None,
                deletion_requested_at=None,
                deletion_actor="",
                purge_after=None,
            )
            Question.objects.filter(revision_id__in=revision_ids).delete()
            QuestionBankRevision.objects.filter(id__in=revision_ids).delete()
            QuestionBank.objects.filter(id__in=bank_ids).delete()
        if series_ids:
            QuestionBankKnowledgePoint.objects.filter(series_id__in=series_ids).delete()
            QuestionBankSeries.objects.filter(id__in=series_ids).delete()
        if document_ids:
            KnowledgeDocument.objects.filter(id__in=document_ids).delete()
    return {
        "documents": len(document_ids),
        "banks": len(bank_ids),
        "series": len(series_ids),
    }


__all__ = [
    "LearningCleanupBatchResult",
    "QuestionBankCleanupResult",
    "cleanup_learning_expired",
    "expire_learning_model_run_reservations",
    "purge_account_learning_data",
    "purge_due_question_bank",
]
