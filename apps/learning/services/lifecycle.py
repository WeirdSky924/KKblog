from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import is_active_account
from apps.learning.contracts import (
    KnowledgeDocumentState,
    KnowledgeReviewRunState,
    LearningCleanupOutcome,
    LearningCommandError,
    LearningDeletionActor,
)
from apps.learning.models import KnowledgeDocument, KnowledgeReviewRun, LearningAppeal
from apps.media.public import MediaStorage, MediaTargetType, release_target_assets

from .review_requests import create_pending_review_run

_FINAL_STATES = (
    KnowledgeDocumentState.CONTENT_PURGED,
    KnowledgeDocumentState.DELETED,
)
_FAILED_STATES = (
    KnowledgeDocumentState.REJECTED,
    KnowledgeDocumentState.REVIEW_FAILED,
)
_REVIEW_STATES = (
    KnowledgeDocumentState.REVIEW_PENDING,
    KnowledgeDocumentState.REVIEWING,
)


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentTransition:
    document_id: UUID
    state: str
    row_version: int


@dataclass(frozen=True, slots=True)
class LearningCleanupResult:
    document_id: UUID
    outcome: LearningCleanupOutcome
    state: str


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "知识文档时间不合法。")
    return current


def _document_identity(value) -> UUID:
    if not isinstance(value, UUID):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    return value


def _locked_owned_document(*, owner_id, document_id) -> KnowledgeDocument:
    if not isinstance(owner_id, UUID) or not is_active_account(owner_id):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    try:
        return KnowledgeDocument.objects.select_for_update().get(
            pk=_document_identity(document_id),
            owner_id=owner_id,
        )
    except KnowledgeDocument.DoesNotExist:
        raise LearningCommandError(
            "learning.document_not_found.v1", "知识文档不存在。"
        ) from None


def _cancel_active_reviews(document: KnowledgeDocument, *, now: datetime) -> None:
    runs = KnowledgeReviewRun.objects.select_for_update().filter(
        document=document,
        state__in=(
            KnowledgeReviewRunState.PENDING,
            KnowledgeReviewRunState.RUNNING,
        ),
    )
    for run in runs:
        run.state = KnowledgeReviewRunState.CANCELLED
        run.safe_reason_code = "owner_delete"
        run.safe_summary = "用户已请求删除知识文档。"
        run.risk_categories = []
        run.completed_at = now
        run.failure_purge_after = None
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


def delete_knowledge_document(
    *,
    owner_id,
    document_id,
    expected_version: int,
    now: datetime | None = None,
) -> KnowledgeDocumentTransition:
    current = _current_time(now)
    with transaction.atomic():
        document = _locked_owned_document(
            owner_id=owner_id,
            document_id=document_id,
        )
        if document.row_version != expected_version:
            raise LearningCommandError(
                "learning.document_conflict.v1", "知识文档已被其他操作修改。"
            )
        if document.state in (*_FINAL_STATES, KnowledgeDocumentState.DELETE_PENDING):
            raise LearningCommandError(
                "learning.document_delete_conflict.v1", "知识文档不能进入删除流程。"
            )
        previous_state = document.state
        _cancel_active_reviews(document, now=current)
        document.state = KnowledgeDocumentState.DELETE_PENDING
        document.pre_delete_state = previous_state
        document.deletion_requested_at = current
        document.deletion_actor = LearningDeletionActor.OWNER
        document.purge_after = current + timedelta(days=7)
        document.row_version += 1
        document.save(
            update_fields=(
                "state",
                "pre_delete_state",
                "deletion_requested_at",
                "deletion_actor",
                "purge_after",
                "row_version",
                "updated_at",
            )
        )
    return KnowledgeDocumentTransition(
        document.id, document.state, document.row_version
    )


def restore_knowledge_document(
    *,
    owner_id,
    document_id,
    expected_version: int,
    now: datetime | None = None,
) -> KnowledgeDocumentTransition:
    current = _current_time(now)
    with transaction.atomic():
        document = _locked_owned_document(
            owner_id=owner_id,
            document_id=document_id,
        )
        if (
            document.row_version != expected_version
            or document.state != KnowledgeDocumentState.DELETE_PENDING
            or document.deletion_actor == LearningDeletionActor.ADMINISTRATOR
            or document.purge_after is None
            or current >= document.purge_after
        ):
            raise LearningCommandError(
                "learning.document_restore_expired.v1",
                "知识文档已无法恢复。",
            )
        restored_state = document.pre_delete_state
        if restored_state in _REVIEW_STATES:
            restored_state = KnowledgeDocumentState.REVIEW_PENDING
            create_pending_review_run(document)
        document.state = restored_state
        document.pre_delete_state = None
        document.deletion_requested_at = None
        document.deletion_actor = ""
        document.purge_after = None
        document.row_version += 1
        document.save(
            update_fields=(
                "state",
                "pre_delete_state",
                "deletion_requested_at",
                "deletion_actor",
                "purge_after",
                "row_version",
                "updated_at",
            )
        )
    return KnowledgeDocumentTransition(
        document.id, document.state, document.row_version
    )


def _clear_document_content(
    document: KnowledgeDocument,
    *,
    state: KnowledgeDocumentState,
    now: datetime,
) -> None:
    document.review_runs.update(
        input_content_sha256=None,
        safe_summary=None,
        risk_categories=[],
    )
    document.state = state
    document.media_asset_id = None
    document.original_name = None
    document.title = None
    document.summary = None
    document.content_sha256 = None
    document.character_count = None
    document.line_count = None
    document.estimated_tokens = None
    document.statement_version = None
    document.statement_accepted_by = None
    document.statement_accepted_at = None
    document.safe_status_summary = None
    document.admin_lock_reason = ""
    document.admin_hidden_at = None
    document.pre_delete_state = None
    document.deletion_requested_at = None
    document.deletion_actor = ""
    document.purge_after = None
    document.failure_purge_after = None
    document.content_purged_at = now
    document.deleted_at = now if state == KnowledgeDocumentState.DELETED else None
    document.row_version += 1
    document.save()


def purge_due_knowledge_document(
    *,
    document_id,
    now: datetime | None = None,
    storage: MediaStorage | None = None,
) -> LearningCleanupResult:
    identity = _document_identity(document_id)
    current = _current_time(now)
    with transaction.atomic():
        try:
            document = KnowledgeDocument.objects.select_for_update().get(pk=identity)
        except KnowledgeDocument.DoesNotExist:
            raise LearningCommandError(
                "learning.document_not_found.v1", "知识文档不存在。"
            ) from None
        if document.state == KnowledgeDocumentState.DELETED:
            return LearningCleanupResult(
                document.id,
                LearningCleanupOutcome.ALREADY_PURGED,
                document.state,
            )
        if (
            document.state != KnowledgeDocumentState.DELETE_PENDING
            or document.purge_after is None
            or current < document.purge_after
            or LearningAppeal.objects.filter(
                document=document,
                state="PENDING",
            ).exists()
        ):
            return LearningCleanupResult(
                document.id,
                LearningCleanupOutcome.NOT_DUE,
                document.state,
            )
        release_target_assets(
            target_type=MediaTargetType.LEARNING_DOCUMENT,
            target_ids=(str(document.id),),
            storage=storage,
        )
        _clear_document_content(
            document,
            state=KnowledgeDocumentState.DELETED,
            now=current,
        )
    return LearningCleanupResult(
        document.id,
        LearningCleanupOutcome.DELETED,
        document.state,
    )


def purge_failed_knowledge_document(
    *,
    document_id,
    now: datetime | None = None,
    storage: MediaStorage | None = None,
) -> LearningCleanupResult:
    identity = _document_identity(document_id)
    current = _current_time(now)
    with transaction.atomic():
        try:
            document = KnowledgeDocument.objects.select_for_update().get(pk=identity)
        except KnowledgeDocument.DoesNotExist:
            raise LearningCommandError(
                "learning.document_not_found.v1", "知识文档不存在。"
            ) from None
        if document.state == KnowledgeDocumentState.CONTENT_PURGED:
            return LearningCleanupResult(
                document.id,
                LearningCleanupOutcome.ALREADY_PURGED,
                document.state,
            )
        if (
            document.state not in _FAILED_STATES
            or document.failure_purge_after is None
            or current < document.failure_purge_after
        ):
            return LearningCleanupResult(
                document.id,
                LearningCleanupOutcome.NOT_DUE,
                document.state,
            )
        release_target_assets(
            target_type=MediaTargetType.LEARNING_DOCUMENT,
            target_ids=(str(document.id),),
            storage=storage,
        )
        _clear_document_content(
            document,
            state=KnowledgeDocumentState.CONTENT_PURGED,
            now=current,
        )
    return LearningCleanupResult(
        document.id,
        LearningCleanupOutcome.CONTENT_PURGED,
        document.state,
    )
