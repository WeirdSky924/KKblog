import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import is_administrator
from apps.core.events import enqueue_event
from apps.learning.contracts import (
    LEARNING_ADMIN_REASON_CODES,
    AdminLearningAction,
    KnowledgeDocumentState,
    LearningAdminTargetType,
    LearningCommandError,
    LearningDeletionActor,
    QuestionBankVisibility,
)
from apps.learning.events import DOCUMENT_ADMINISTRATION_CHANGED
from apps.learning.models import KnowledgeDocument, QuestionBank
from apps.operations.public import record_audit_entry

from .bank_lifecycle import (
    delete_question_bank,
    restore_question_bank,
    set_question_bank_visibility,
)
from .lifecycle import _cancel_active_reviews
from .review_requests import create_pending_review_run

MAX_ADMIN_BATCH_TARGETS = 50
_REASON_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_TRACE_CODE = re.compile(r"^trc_[0-9a-hjkmnp-tv-z]{26}$")
_FINAL_DOCUMENT_STATES = {
    KnowledgeDocumentState.CONTENT_PURGED,
    KnowledgeDocumentState.DELETED,
}
_REVIEW_DOCUMENT_STATES = {
    KnowledgeDocumentState.REVIEW_PENDING,
    KnowledgeDocumentState.REVIEWING,
}


@dataclass(frozen=True, slots=True)
class AdminLearningTarget:
    target_id: UUID
    row_version: int


@dataclass(frozen=True, slots=True)
class AdminLearningItemResult:
    target_id: UUID
    target_type: str
    action: str
    state: str
    row_version: int
    admin_hidden: bool
    succeeded: bool = True
    error_code: str = ""
    safe_message: str = ""


@dataclass(frozen=True, slots=True)
class AdminLearningBatchPreflight:
    target_type: str
    action: str
    total: int
    executable: int
    state_counts: dict[str, int]
    items: tuple[AdminLearningItemResult, ...]


@dataclass(frozen=True, slots=True)
class AdminLearningBatchResult:
    target_type: str
    action: str
    total: int
    succeeded: int
    failed: int
    items: tuple[AdminLearningItemResult, ...]


def _administrator(value) -> UUID:
    if not isinstance(value, UUID) or not is_administrator(value):
        raise LearningCommandError(
            "learning.administrator_required.v1", "需要管理员权限。"
        )
    return value


def _current_time(value: datetime | None) -> datetime:
    current = value or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "管理操作时间不合法。")
    return current


def _action(value) -> AdminLearningAction:
    try:
        return AdminLearningAction(value)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.administration_invalid.v1", "管理操作不合法。"
        ) from None


def _target_type(value) -> LearningAdminTargetType:
    try:
        return LearningAdminTargetType(value)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.administration_invalid.v1", "管理目标不合法。"
        ) from None


def _meta(*, trace_code, client_ip) -> tuple[str, str]:
    if (
        not isinstance(trace_code, str)
        or _TRACE_CODE.fullmatch(trace_code) is None
        or not isinstance(client_ip, str)
        or not client_ip
    ):
        raise LearningCommandError(
            "learning.administration_invalid.v1", "管理操作信息不合法。"
        )
    return trace_code, client_ip


def _reason(value: str, *, required: bool) -> str:
    if not required and value == "":
        return ""
    if (
        not isinstance(value, str)
        or _REASON_CODE.fullmatch(value) is None
        or value not in LEARNING_ADMIN_REASON_CODES
    ):
        raise LearningCommandError(
            "learning.administration_invalid.v1", "管理原因不合法。"
        )
    return value


def _document_snapshot(document: KnowledgeDocument) -> dict[str, object]:
    return {
        "state": document.state,
        "admin_lock_reason": document.admin_lock_reason,
        "deletion_actor": document.deletion_actor,
        "row_version": document.row_version,
    }


def _document_result(
    document: KnowledgeDocument,
    *,
    action: AdminLearningAction,
) -> AdminLearningItemResult:
    return AdminLearningItemResult(
        target_id=document.id,
        target_type=LearningAdminTargetType.DOCUMENT,
        action=action,
        state=document.state,
        row_version=document.row_version,
        admin_hidden=document.admin_hidden_at is not None,
    )


def administer_knowledge_document(
    *,
    administrator_id,
    document_id,
    expected_version: int,
    action,
    reason_code: str = "",
    trace_code: str,
    client_ip: str,
    now: datetime | None = None,
) -> AdminLearningItemResult:
    actor = _administrator(administrator_id)
    selected_action = _action(action)
    trace, ip = _meta(trace_code=trace_code, client_ip=client_ip)
    reason = _reason(
        reason_code,
        required=selected_action
        in {AdminLearningAction.HIDE, AdminLearningAction.DELETE},
    )
    current = _current_time(now)
    if not isinstance(document_id, UUID):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    with transaction.atomic():
        try:
            document = KnowledgeDocument.objects.select_for_update().get(pk=document_id)
        except KnowledgeDocument.DoesNotExist:
            raise LearningCommandError(
                "learning.document_not_found.v1", "知识文档不存在。"
            ) from None
        if document.row_version != expected_version:
            raise LearningCommandError(
                "learning.document_conflict.v1", "知识文档已被其他操作修改。"
            )
        before = _document_snapshot(document)
        if selected_action == AdminLearningAction.HIDE:
            if (
                document.state
                in (*_FINAL_DOCUMENT_STATES, KnowledgeDocumentState.DELETE_PENDING)
                or document.admin_hidden_at is not None
            ):
                raise LearningCommandError(
                    "learning.document_administration_conflict.v1",
                    "知识文档当前不能隐藏。",
                )
            document.admin_hidden_at = current
            document.admin_lock_reason = reason
        elif selected_action == AdminLearningAction.DELETE:
            if document.state in (
                *_FINAL_DOCUMENT_STATES,
                KnowledgeDocumentState.DELETE_PENDING,
            ):
                raise LearningCommandError(
                    "learning.document_administration_conflict.v1",
                    "知识文档当前不能删除。",
                )
            previous_state = document.state
            _cancel_active_reviews(document, now=current)
            document.state = KnowledgeDocumentState.DELETE_PENDING
            document.pre_delete_state = previous_state
            document.deletion_requested_at = current
            document.deletion_actor = LearningDeletionActor.ADMINISTRATOR
            document.purge_after = current + timedelta(days=7)
            document.admin_lock_reason = reason
        else:
            if (
                document.state == KnowledgeDocumentState.DELETE_PENDING
                and document.deletion_actor == LearningDeletionActor.ADMINISTRATOR
                and document.purge_after is not None
                and current < document.purge_after
            ):
                restored_state = document.pre_delete_state
                if restored_state in _REVIEW_DOCUMENT_STATES:
                    restored_state = KnowledgeDocumentState.REVIEW_PENDING
                    create_pending_review_run(document)
                document.state = restored_state
                document.pre_delete_state = None
                document.deletion_requested_at = None
                document.deletion_actor = ""
                document.purge_after = None
                if document.admin_hidden_at is None:
                    document.admin_lock_reason = ""
            elif document.admin_hidden_at is not None:
                document.admin_hidden_at = None
                document.admin_lock_reason = ""
            else:
                raise LearningCommandError(
                    "learning.document_administration_conflict.v1",
                    "知识文档当前不能恢复。",
                )
        document.row_version += 1
        document.save()
        record_audit_entry(
            action=f"learning.document.admin.{selected_action.value.casefold()}",
            actor_id=actor,
            target_id=str(document.id),
            trace_code=trace,
            client_ip=ip,
            before=before,
            after=_document_snapshot(document),
            summary=f"{selected_action.value.title()} knowledge document",
        )
        enqueue_event(
            DOCUMENT_ADMINISTRATION_CHANGED,
            aggregate_type="knowledge_document",
            aggregate_id=str(document.id),
            payload={
                "recipient_id": str(document.owner_id),
                "action": selected_action.value,
            },
        )
    return _document_result(document, action=selected_action)


def _bank_result(bank: QuestionBank, *, action: AdminLearningAction):
    return AdminLearningItemResult(
        target_id=bank.id,
        target_type=LearningAdminTargetType.QUESTION_BANK,
        action=action,
        state=bank.visibility,
        row_version=bank.row_version,
        admin_hidden=bank.visibility == QuestionBankVisibility.ADMIN_HIDDEN,
    )


def administer_question_bank(
    *,
    administrator_id,
    bank_id,
    expected_version: int,
    action,
    reason_code: str = "",
    trace_code: str,
    client_ip: str,
    now: datetime | None = None,
) -> AdminLearningItemResult:
    actor = _administrator(administrator_id)
    selected_action = _action(action)
    trace, ip = _meta(trace_code=trace_code, client_ip=client_ip)
    reason = _reason(
        reason_code,
        required=selected_action
        in {AdminLearningAction.HIDE, AdminLearningAction.DELETE},
    )
    try:
        bank = QuestionBank.objects.get(pk=bank_id)
    except (QuestionBank.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    if selected_action == AdminLearningAction.HIDE:
        bank = set_question_bank_visibility(
            actor_id=actor,
            bank_id=bank.id,
            expected_version=expected_version,
            target=QuestionBankVisibility.ADMIN_HIDDEN,
            reason_code=reason,
            trace_code=trace,
            client_ip=ip,
        )
    elif selected_action == AdminLearningAction.DELETE:
        bank = delete_question_bank(
            actor_id=actor,
            bank_id=bank.id,
            expected_version=expected_version,
            reason_code=reason,
            trace_code=trace,
            client_ip=ip,
            now=now,
        )
    else:
        if bank.visibility == QuestionBankVisibility.ADMIN_HIDDEN:
            bank = set_question_bank_visibility(
                actor_id=actor,
                bank_id=bank.id,
                expected_version=expected_version,
                target=QuestionBankVisibility.PUBLISHED,
                trace_code=trace,
                client_ip=ip,
            )
        elif (
            bank.visibility == QuestionBankVisibility.DELETE_PENDING
            and bank.deletion_actor == LearningDeletionActor.ADMINISTRATOR
        ):
            bank = restore_question_bank(
                actor_id=actor,
                bank_id=bank.id,
                expected_version=expected_version,
                trace_code=trace,
                client_ip=ip,
                now=now,
            )
        else:
            raise LearningCommandError(
                "learning.bank_administration_conflict.v1",
                "题库当前不能恢复。",
            )
    return _bank_result(bank, action=selected_action)


def _targets(value) -> tuple[AdminLearningTarget, ...]:
    if (
        not isinstance(value, (tuple, list))
        or not 1 <= len(value) <= MAX_ADMIN_BATCH_TARGETS
    ):
        raise LearningCommandError("learning.batch_invalid.v1", "批量目标数量不合法。")
    normalized = []
    seen = set()
    for target in value:
        if not isinstance(target, AdminLearningTarget):
            raise LearningCommandError("learning.batch_invalid.v1", "批量目标不合法。")
        if (
            not isinstance(target.target_id, UUID)
            or isinstance(target.row_version, bool)
            or not isinstance(target.row_version, int)
            or target.row_version < 1
            or target.target_id in seen
        ):
            raise LearningCommandError("learning.batch_invalid.v1", "批量目标不合法。")
        seen.add(target.target_id)
        normalized.append(target)
    return tuple(normalized)


def _preflight_item(target, *, target_type, action, state, executable, message=""):
    return AdminLearningItemResult(
        target_id=target.target_id,
        target_type=target_type,
        action=action,
        state=state,
        row_version=target.row_version,
        admin_hidden=state == QuestionBankVisibility.ADMIN_HIDDEN,
        succeeded=executable,
        error_code="" if executable else "learning.batch_target_conflict.v1",
        safe_message="" if executable else message,
    )


def preflight_learning_admin_batch(
    *,
    administrator_id,
    target_type,
    action,
    targets,
) -> AdminLearningBatchPreflight:
    _administrator(administrator_id)
    normalized_type = _target_type(target_type)
    normalized_action = _action(action)
    selected = _targets(targets)
    if normalized_type == LearningAdminTargetType.DOCUMENT:
        rows = {
            row.id: row
            for row in KnowledgeDocument.objects.filter(
                id__in=[target.target_id for target in selected]
            )
        }
    else:
        rows = {
            row.id: row
            for row in QuestionBank.objects.filter(
                id__in=[target.target_id for target in selected]
            )
        }
    items = []
    state_counts: dict[str, int] = {}
    for target in selected:
        row = rows.get(target.target_id)
        if row is None:
            state = "NOT_FOUND"
        elif normalized_type == LearningAdminTargetType.DOCUMENT:
            state = row.state
        else:
            state = row.visibility
        state_counts[state] = state_counts.get(state, 0) + 1
        if row is None or row.row_version != target.row_version:
            items.append(
                _preflight_item(
                    target,
                    target_type=normalized_type,
                    action=normalized_action,
                    state=state,
                    executable=False,
                    message="对象已不存在或版本已变化。",
                )
            )
            continue
        if normalized_type == LearningAdminTargetType.DOCUMENT:
            executable = (
                (
                    normalized_action == AdminLearningAction.HIDE
                    and row.state
                    not in (
                        *_FINAL_DOCUMENT_STATES,
                        KnowledgeDocumentState.DELETE_PENDING,
                    )
                    and row.admin_hidden_at is None
                )
                or (
                    normalized_action == AdminLearningAction.DELETE
                    and row.state
                    not in (
                        *_FINAL_DOCUMENT_STATES,
                        KnowledgeDocumentState.DELETE_PENDING,
                    )
                )
                or (
                    normalized_action == AdminLearningAction.RESTORE
                    and (
                        row.admin_hidden_at is not None
                        or (
                            row.state == KnowledgeDocumentState.DELETE_PENDING
                            and row.deletion_actor
                            == LearningDeletionActor.ADMINISTRATOR
                        )
                    )
                )
            )
        else:
            executable = (
                (
                    normalized_action == AdminLearningAction.HIDE
                    and row.visibility
                    in {
                        QuestionBankVisibility.PUBLISHED,
                        QuestionBankVisibility.OWNER_HIDDEN,
                    }
                )
                or (
                    normalized_action == AdminLearningAction.DELETE
                    and row.visibility
                    in {
                        QuestionBankVisibility.PUBLISHED,
                        QuestionBankVisibility.OWNER_HIDDEN,
                        QuestionBankVisibility.ADMIN_HIDDEN,
                    }
                )
                or (
                    normalized_action == AdminLearningAction.RESTORE
                    and (
                        row.visibility == QuestionBankVisibility.ADMIN_HIDDEN
                        or (
                            row.visibility == QuestionBankVisibility.DELETE_PENDING
                            and row.deletion_actor
                            == LearningDeletionActor.ADMINISTRATOR
                        )
                    )
                )
            )
        items.append(
            _preflight_item(
                target,
                target_type=normalized_type,
                action=normalized_action,
                state=state,
                executable=executable,
                message="对象当前状态不支持该操作。",
            )
        )
    return AdminLearningBatchPreflight(
        target_type=normalized_type,
        action=normalized_action,
        total=len(items),
        executable=sum(item.succeeded for item in items),
        state_counts=state_counts,
        items=tuple(items),
    )


def execute_learning_admin_batch(
    *,
    administrator_id,
    target_type,
    action,
    targets,
    reason_code: str = "",
    trace_code: str,
    client_ip: str,
    now: datetime | None = None,
) -> AdminLearningBatchResult:
    actor = _administrator(administrator_id)
    normalized_type = _target_type(target_type)
    normalized_action = _action(action)
    selected = _targets(targets)
    results = []
    for target in selected:
        try:
            if normalized_type == LearningAdminTargetType.DOCUMENT:
                result = administer_knowledge_document(
                    administrator_id=actor,
                    document_id=target.target_id,
                    expected_version=target.row_version,
                    action=normalized_action,
                    reason_code=reason_code,
                    trace_code=trace_code,
                    client_ip=client_ip,
                    now=now,
                )
            else:
                result = administer_question_bank(
                    administrator_id=actor,
                    bank_id=target.target_id,
                    expected_version=target.row_version,
                    action=normalized_action,
                    reason_code=reason_code,
                    trace_code=trace_code,
                    client_ip=client_ip,
                    now=now,
                )
        except LearningCommandError as error:
            results.append(
                AdminLearningItemResult(
                    target_id=target.target_id,
                    target_type=normalized_type,
                    action=normalized_action,
                    state="ERROR",
                    row_version=target.row_version,
                    admin_hidden=False,
                    succeeded=False,
                    error_code=error.code,
                    safe_message=str(error),
                )
            )
        else:
            results.append(result)
    succeeded = sum(item.succeeded for item in results)
    return AdminLearningBatchResult(
        target_type=normalized_type,
        action=normalized_action,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        items=tuple(results),
    )


__all__ = [
    "AdminLearningBatchPreflight",
    "AdminLearningBatchResult",
    "AdminLearningItemResult",
    "AdminLearningTarget",
    "MAX_ADMIN_BATCH_TARGETS",
    "administer_knowledge_document",
    "administer_question_bank",
    "execute_learning_admin_batch",
    "preflight_learning_admin_batch",
]
