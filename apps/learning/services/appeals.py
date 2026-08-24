from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.public import (
    can_upload_attachments,
    is_active_account,
    is_administrator,
)
from apps.core.events import enqueue_event
from apps.learning.contracts import (
    KnowledgeDocumentState,
    LearningAdminTargetType,
    LearningAppealDecision,
    LearningAppealState,
    LearningCommandError,
)
from apps.learning.events import APPEAL_APPROVED, APPEAL_REJECTED
from apps.learning.models import KnowledgeDocument, LearningAppeal, QuestionBank
from apps.learning.policies import locked_account_quota_state
from apps.media.public import RenderingError, render_markdown
from apps.operations.public import record_audit_entry

from .dispatch import ReviewDispatcher
from .review_requests import retry_document_review_locked

MAX_APPEAL_MARKDOWN_LENGTH = 4_000


@dataclass(frozen=True, slots=True)
class LearningAppealResult:
    appeal_id: UUID
    document_id: UUID | None
    bank_id: UUID | None
    target_type: str
    target_id: UUID
    state: str
    reason_html: str
    decision_html: str
    row_version: int


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "申诉时间不合法。")
    return current


def _markdown(value: str, *, field: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise LearningCommandError("learning.appeal_invalid.v1", f"{field}不合法。")
    normalized = value.strip()
    if not 1 <= len(normalized) <= MAX_APPEAL_MARKDOWN_LENGTH:
        raise LearningCommandError("learning.appeal_invalid.v1", f"{field}不合法。")
    try:
        rendered = render_markdown(normalized)
    except RenderingError:
        raise LearningCommandError(
            "learning.appeal_invalid.v1", f"{field}不合法。"
        ) from None
    return normalized, rendered.html


def _result(appeal: LearningAppeal) -> LearningAppealResult:
    _, reason_html = _markdown(appeal.reason_markdown, field="申诉理由")
    decision_html = ""
    if appeal.decision_markdown:
        _, decision_html = _markdown(appeal.decision_markdown, field="决定说明")
    document_id = appeal.document_id
    bank_id = appeal.question_bank_id
    target_type = (
        LearningAdminTargetType.DOCUMENT
        if document_id is not None
        else LearningAdminTargetType.QUESTION_BANK
    )
    return LearningAppealResult(
        appeal.id,
        document_id,
        bank_id,
        target_type,
        document_id or bank_id,
        appeal.state,
        reason_html,
        decision_html,
        appeal.row_version,
    )


def submit_learning_appeal(
    *,
    owner_id,
    document_id,
    expected_document_version: int,
    reason_markdown: str,
    now: datetime | None = None,
) -> LearningAppealResult:
    if (
        not isinstance(owner_id, UUID)
        or not isinstance(document_id, UUID)
        or not can_upload_attachments(owner_id)
    ):
        raise LearningCommandError(
            "learning.appeal_not_available.v1", "知识文档当前不能申诉。"
        )
    current = _current_time(now)
    reason, _ = _markdown(reason_markdown, field="申诉理由")
    try:
        with transaction.atomic():
            try:
                document = KnowledgeDocument.objects.select_for_update().get(
                    pk=document_id,
                    owner_id=owner_id,
                )
            except KnowledgeDocument.DoesNotExist:
                raise LearningCommandError(
                    "learning.document_not_found.v1", "知识文档不存在。"
                ) from None
            if document.row_version != expected_document_version or not (
                (
                    document.state == KnowledgeDocumentState.REJECTED
                    and document.failure_purge_after is not None
                    and current < document.failure_purge_after
                )
                or document.admin_hidden_at is not None
                or (
                    document.state == KnowledgeDocumentState.DELETE_PENDING
                    and document.deletion_actor == "ADMIN"
                    and document.purge_after is not None
                    and current < document.purge_after
                )
            ):
                raise LearningCommandError(
                    "learning.appeal_not_available.v1", "知识文档当前不能申诉。"
                )
            if LearningAppeal.objects.filter(
                document=document,
                state=LearningAppealState.PENDING,
            ).exists():
                raise LearningCommandError(
                    "learning.appeal_pending.v1", "知识文档已有待处理申诉。"
                )
            appeal = LearningAppeal.objects.create(
                document=document,
                appellant_id=owner_id,
                target_row_version=document.row_version,
                reason_markdown=reason,
            )
    except IntegrityError as exc:
        raise LearningCommandError(
            "learning.appeal_pending.v1", "知识文档已有待处理申诉。"
        ) from exc
    return _result(appeal)


def submit_question_bank_appeal(
    *,
    owner_id,
    bank_id,
    expected_bank_version: int,
    reason_markdown: str,
    now: datetime | None = None,
) -> LearningAppealResult:
    if not isinstance(owner_id, UUID) or not isinstance(bank_id, UUID):
        raise LearningCommandError(
            "learning.appeal_not_available.v1", "题库当前不能申诉。"
        )
    current = _current_time(now)
    reason, _ = _markdown(reason_markdown, field="申诉理由")
    with transaction.atomic():
        try:
            bank = (
                QuestionBank.objects.select_for_update()
                .select_related("series")
                .get(
                    pk=bank_id,
                    series__owner_id=owner_id,
                )
            )
        except QuestionBank.DoesNotExist:
            raise LearningCommandError(
                "learning.bank_not_found.v1", "题库不存在。"
            ) from None
        if not is_active_account(owner_id) or (
            bank.row_version != expected_bank_version
            or not (
                bank.visibility == "ADMIN_HIDDEN"
                or (
                    bank.visibility == "DELETE_PENDING"
                    and bank.deletion_actor == "ADMIN"
                    and bank.purge_after is not None
                    and current < bank.purge_after
                )
            )
        ):
            raise LearningCommandError(
                "learning.appeal_not_available.v1", "题库当前不能申诉。"
            )
        if LearningAppeal.objects.filter(
            question_bank=bank,
            state=LearningAppealState.PENDING,
        ).exists():
            raise LearningCommandError(
                "learning.appeal_pending.v1", "题库已有待处理申诉。"
            )
        try:
            appeal = LearningAppeal.objects.create(
                question_bank=bank,
                appellant_id=owner_id,
                target_row_version=bank.row_version,
                reason_markdown=reason,
            )
        except IntegrityError as exc:
            raise LearningCommandError(
                "learning.appeal_pending.v1", "题库已有待处理申诉。"
            ) from exc
    return _result(appeal)


def withdraw_learning_appeal(
    *,
    owner_id,
    appeal_id,
    expected_version: int,
    now: datetime | None = None,
) -> LearningAppealResult:
    if not isinstance(owner_id, UUID) or not isinstance(appeal_id, UUID):
        raise LearningCommandError("learning.appeal_not_found.v1", "申诉不存在。")
    current = _current_time(now)
    with transaction.atomic():
        try:
            appeal = LearningAppeal.objects.select_for_update().get(
                pk=appeal_id,
                appellant_id=owner_id,
            )
        except LearningAppeal.DoesNotExist:
            raise LearningCommandError(
                "learning.appeal_not_found.v1", "申诉不存在。"
            ) from None
        if appeal.row_version != expected_version or appeal.state != "PENDING":
            raise LearningCommandError(
                "learning.appeal_conflict.v1", "申诉已被其他操作修改。"
            )
        appeal.state = LearningAppealState.WITHDRAWN
        appeal.withdrawn_at = current
        appeal.row_version += 1
        appeal.save()
    return _result(appeal)


def review_learning_appeal(
    *,
    administrator_id,
    appeal_id,
    expected_version: int,
    decision,
    decision_markdown: str,
    dispatcher: ReviewDispatcher,
    trace_code: str,
    client_ip: str,
    now: datetime | None = None,
) -> LearningAppealResult:
    if (
        not isinstance(administrator_id, UUID)
        or not is_administrator(administrator_id)
        or not isinstance(appeal_id, UUID)
        or not callable(dispatcher)
    ):
        raise LearningCommandError(
            "learning.administrator_required.v1", "需要管理员权限。"
        )
    try:
        normalized_decision = LearningAppealDecision(decision)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.appeal_invalid.v1", "申诉决定不合法。"
        ) from None
    current = _current_time(now)
    decision_source, _ = _markdown(decision_markdown, field="决定说明")
    try:
        candidate = LearningAppeal.objects.select_related(
            "document", "question_bank"
        ).get(pk=appeal_id)
    except LearningAppeal.DoesNotExist:
        raise LearningCommandError(
            "learning.appeal_not_found.v1", "申诉不存在。"
        ) from None
    with transaction.atomic():
        owner_id = (
            candidate.document.owner_id
            if candidate.document_id is not None
            else candidate.question_bank.series.owner_id
        )
        locked_account_quota_state(owner_id)
        appeal = LearningAppeal.objects.select_for_update().get(pk=appeal_id)
        document = (
            KnowledgeDocument.objects.select_for_update().get(pk=appeal.document_id)
            if appeal.document_id is not None
            else None
        )
        bank = (
            QuestionBank.objects.select_for_update()
            .select_related("series")
            .get(pk=appeal.question_bank_id)
            if appeal.question_bank_id is not None
            else None
        )
        target_version = (
            document.row_version if document is not None else bank.row_version
        )
        if (
            appeal.row_version != expected_version
            or appeal.state != LearningAppealState.PENDING
            or target_version != appeal.target_row_version
        ):
            raise LearningCommandError(
                "learning.appeal_conflict.v1", "申诉已被其他操作修改。"
            )
        if normalized_decision == LearningAppealDecision.APPROVED:
            if (
                document is not None
                and document.state == KnowledgeDocumentState.REJECTED
            ):
                retry_document_review_locked(
                    document=document,
                    dispatcher=dispatcher,
                    current=current,
                    ignore_appeal_id=appeal.id,
                )
            elif document is not None:
                from .administration import administer_knowledge_document

                administer_knowledge_document(
                    administrator_id=administrator_id,
                    document_id=document.id,
                    expected_version=document.row_version,
                    action="RESTORE",
                    trace_code=trace_code,
                    client_ip=client_ip,
                    now=current,
                )
            elif bank is not None:
                from .administration import administer_question_bank

                administer_question_bank(
                    administrator_id=administrator_id,
                    bank_id=bank.id,
                    expected_version=bank.row_version,
                    action="RESTORE",
                    trace_code=trace_code,
                    client_ip=client_ip,
                    now=current,
                )
        appeal.state = LearningAppealState(normalized_decision.value)
        appeal.decision_markdown = decision_source
        appeal.decided_by_id = administrator_id
        appeal.decided_at = current
        appeal.row_version += 1
        appeal.save()
        record_audit_entry(
            action="learning.appeal.review",
            actor_id=administrator_id,
            target_id=str(appeal.id),
            trace_code=trace_code,
            client_ip=client_ip,
            before={
                "state": LearningAppealState.PENDING,
                "row_version": expected_version,
            },
            after={"state": appeal.state, "row_version": appeal.row_version},
            summary="Review learning appeal",
        )
        event = (
            APPEAL_APPROVED
            if normalized_decision == LearningAppealDecision.APPROVED
            else APPEAL_REJECTED
        )
        enqueue_event(
            event,
            aggregate_type="learning_appeal",
            aggregate_id=str(appeal.id),
            payload={"recipient_id": str(appeal.appellant_id)},
        )
    return _result(appeal)


__all__ = [
    "LearningAppealResult",
    "MAX_APPEAL_MARKDOWN_LENGTH",
    "review_learning_appeal",
    "submit_learning_appeal",
    "withdraw_learning_appeal",
]
