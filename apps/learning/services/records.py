from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import is_active_account, lock_active_account
from apps.learning.contracts import (
    LearningCommandError,
    QuizAttemptStatus,
    QuizMasteryStatus,
)
from apps.learning.models import QuizAttempt, QuizResponse, WrongQuestion

DELETE_COOLING_PERIOD = timedelta(days=7)
MAX_RECORD_BATCH = 50


@dataclass(frozen=True, slots=True)
class WrongQuestionMutationResult:
    wrong_question_id: UUID
    mastery_status: str
    row_version: int
    changed: bool


@dataclass(frozen=True, slots=True)
class QuizRecordMutationResult:
    attempt_id: UUID
    status: str
    row_version: int
    deletion_requested_at: datetime | None
    purge_after: datetime | None
    changed: bool


@dataclass(frozen=True, slots=True)
class QuizRecordBatchItem:
    attempt_id: UUID
    outcome: str
    row_version: int | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class QuizRecordBatchResult:
    requested_count: int
    succeeded_count: int
    items: tuple[QuizRecordBatchItem, ...]


def _owner(account_id) -> UUID:
    if not isinstance(account_id, UUID) or not is_active_account(account_id):
        raise LearningCommandError("learning.quiz_login_required.v1", "请先登录。")
    return account_id


def _now(value: datetime | None) -> datetime:
    current = value or timezone.now()
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise LearningCommandError("learning.quiz_time_invalid.v1", "答题时间不合法。")
    return current


def _lock_account(account_id: UUID) -> None:
    if not lock_active_account(account_id):
        raise LearningCommandError("learning.quiz_login_required.v1", "请先登录。")


def _mastery(value) -> str:
    try:
        return QuizMasteryStatus(value).value
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.quiz_mastery_invalid.v1", "掌握状态不合法。"
        ) from None


def set_wrong_question_mastery(
    *, account_id, wrong_question_id, expected_version: int, mastery_status, now=None
) -> WrongQuestionMutationResult:
    account_id = _owner(account_id)
    target = _mastery(mastery_status)
    current = _now(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            wrong = WrongQuestion.objects.select_for_update().get(
                pk=wrong_question_id, account_id=account_id
            )
        except (WrongQuestion.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.wrong_question_not_found.v1", "错题不存在。"
            ) from None
        if wrong.row_version != expected_version:
            raise LearningCommandError(
                "learning.wrong_question_conflict.v1", "错题状态已更新，请刷新后重试。"
            )
        if wrong.mastery_status == target:
            return WrongQuestionMutationResult(
                wrong.id, target, wrong.row_version, False
            )
        wrong.mastery_status = target
        wrong.status_changed_at = current
        wrong.row_version += 1
        wrong.save(update_fields=("mastery_status", "status_changed_at", "row_version"))
    return WrongQuestionMutationResult(wrong.id, target, wrong.row_version, True)


def _record_result(attempt: QuizAttempt, *, changed: bool) -> QuizRecordMutationResult:
    return QuizRecordMutationResult(
        attempt.id,
        attempt.status,
        attempt.row_version,
        attempt.deletion_requested_at,
        attempt.purge_after,
        changed,
    )


def request_quiz_record_deletion(
    *, account_id, attempt_id, expected_version: int, now=None
) -> QuizRecordMutationResult:
    account_id = _owner(account_id)
    current = _now(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            attempt = QuizAttempt.objects.select_for_update().get(
                pk=attempt_id, account_id=account_id
            )
        except (QuizAttempt.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if attempt.status == QuizAttemptStatus.DELETED:
            raise LearningCommandError(
                "learning.quiz_record_deleted.v1", "答题记录已删除。"
            )
        if attempt.status == QuizAttemptStatus.DELETE_PENDING:
            return _record_result(attempt, changed=False)
        if attempt.row_version != expected_version:
            raise LearningCommandError(
                "learning.quiz_record_conflict.v1", "答题记录已更新，请刷新后重试。"
            )
        if attempt.status not in {
            QuizAttemptStatus.IN_PROGRESS,
            QuizAttemptStatus.SUBMITTED,
        }:
            raise LearningCommandError(
                "learning.quiz_record_state_invalid.v1", "答题记录状态不允许删除。"
            )
        attempt.status = QuizAttemptStatus.DELETE_PENDING
        attempt.deletion_requested_at = current
        attempt.purge_after = current + DELETE_COOLING_PERIOD
        attempt.row_version += 1
        attempt.save(
            update_fields=(
                "status",
                "deletion_requested_at",
                "purge_after",
                "row_version",
                "updated_at",
            )
        )
    return _record_result(attempt, changed=True)


def restore_quiz_record(
    *, account_id, attempt_id, expected_version: int, now=None
) -> QuizRecordMutationResult:
    account_id = _owner(account_id)
    current = _now(now)
    with transaction.atomic():
        _lock_account(account_id)
        try:
            attempt = QuizAttempt.objects.select_for_update().get(
                pk=attempt_id, account_id=account_id
            )
        except (QuizAttempt.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if attempt.status != QuizAttemptStatus.DELETE_PENDING:
            raise LearningCommandError(
                "learning.quiz_record_state_invalid.v1", "当前记录不在删除冷静期。"
            )
        if attempt.purge_after is None or current >= attempt.purge_after:
            raise LearningCommandError(
                "learning.quiz_record_expired.v1", "答题记录已超过恢复期限。"
            )
        if attempt.row_version != expected_version:
            raise LearningCommandError(
                "learning.quiz_record_conflict.v1", "答题记录已更新，请刷新后重试。"
            )
        attempt.status = (
            QuizAttemptStatus.SUBMITTED
            if attempt.submitted_at is not None
            else QuizAttemptStatus.IN_PROGRESS
        )
        attempt.deletion_requested_at = None
        attempt.purge_after = None
        attempt.row_version += 1
        attempt.save(
            update_fields=(
                "status",
                "deletion_requested_at",
                "purge_after",
                "row_version",
                "updated_at",
            )
        )
    return _record_result(attempt, changed=True)


def purge_due_quiz_record(*, attempt_id, now=None) -> QuizRecordMutationResult:
    current = _now(now)
    with transaction.atomic():
        try:
            attempt = QuizAttempt.objects.select_for_update().get(pk=attempt_id)
        except (QuizAttempt.DoesNotExist, TypeError, ValueError):
            raise LearningCommandError(
                "learning.quiz_not_found.v1", "答题记录不存在。"
            ) from None
        if attempt.status == QuizAttemptStatus.DELETED:
            return _record_result(attempt, changed=False)
        if (
            attempt.status != QuizAttemptStatus.DELETE_PENDING
            or attempt.purge_after is None
            or current < attempt.purge_after
        ):
            raise LearningCommandError(
                "learning.quiz_record_not_due.v1", "答题记录尚未到清理时间。"
            )
        QuizResponse.objects.filter(attempt_id=attempt.id).delete()
        attempt.status = QuizAttemptStatus.DELETED
        attempt.deleted_at = current
        attempt.deletion_requested_at = None
        attempt.purge_after = None
        attempt.submitted_at = None
        attempt.objective_score = None
        attempt.objective_total = None
        attempt.short_answer_mastered = None
        attempt.short_answer_total = None
        attempt.actual_duration_seconds = None
        attempt.submit_request_id = ""
        attempt.owner_id_snapshot = None
        attempt.bank_title = "已删除答题记录"
        attempt.owner_display_name = "已注销用户"
        attempt.selected_question_types = []
        attempt.question_order = []
        attempt.option_orders = {}
        attempt.row_version += 1
        attempt.save(
            update_fields=(
                "status",
                "deleted_at",
                "deletion_requested_at",
                "purge_after",
                "submitted_at",
                "objective_score",
                "objective_total",
                "short_answer_mastered",
                "short_answer_total",
                "actual_duration_seconds",
                "submit_request_id",
                "owner_id_snapshot",
                "bank_title",
                "owner_display_name",
                "selected_question_types",
                "question_order",
                "option_orders",
                "row_version",
                "updated_at",
            )
        )
    return _record_result(attempt, changed=True)


def _ids(values) -> tuple[UUID, ...]:
    if not isinstance(values, (list, tuple, set)):
        raise LearningCommandError(
            "learning.quiz_batch_invalid.v1", "批量记录参数不合法。"
        )
    normalized = []
    for value in values:
        try:
            item = value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError):
            raise LearningCommandError(
                "learning.quiz_batch_invalid.v1", "批量记录参数不合法。"
            ) from None
        if item not in normalized:
            normalized.append(item)
    if not normalized or len(normalized) > MAX_RECORD_BATCH:
        raise LearningCommandError(
            "learning.quiz_batch_invalid.v1", "批量记录数量不合法。"
        )
    return tuple(normalized)


def quiz_record_delete_preflight(*, account_id, attempt_ids) -> int:
    account_id = _owner(account_id)
    ids = _ids(attempt_ids)
    return QuizAttempt.objects.filter(
        account_id=account_id,
        id__in=ids,
        status__in=(QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED),
    ).count()


def delete_quiz_records(
    *, account_id, attempt_ids, expected_versions: dict, now=None
) -> QuizRecordBatchResult:
    account_id = _owner(account_id)
    ids = _ids(attempt_ids)
    if not isinstance(expected_versions, dict):
        raise LearningCommandError("learning.quiz_batch_invalid.v1", "版本参数不合法。")
    current = _now(now)
    items = []
    for attempt_id in ids:
        try:
            version = int(expected_versions[str(attempt_id)])
            result = request_quiz_record_deletion(
                account_id=account_id,
                attempt_id=attempt_id,
                expected_version=version,
                now=current,
            )
            items.append(
                QuizRecordBatchItem(attempt_id, "deleted", result.row_version, None)
            )
        except (KeyError, TypeError, ValueError):
            items.append(
                QuizRecordBatchItem(
                    attempt_id, "failed", None, "learning.quiz_record_conflict.v1"
                )
            )
        except LearningCommandError as error:
            items.append(QuizRecordBatchItem(attempt_id, "failed", None, error.code))
    return QuizRecordBatchResult(
        len(ids), sum(item.outcome == "deleted" for item in items), tuple(items)
    )


def delete_all_quiz_records(
    *, account_id, expected_count: int, now=None
) -> QuizRecordBatchResult:
    account_id = _owner(account_id)
    if (
        isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or expected_count < 0
    ):
        raise LearningCommandError("learning.quiz_batch_invalid.v1", "确认数量不合法。")
    current = _now(now)
    with transaction.atomic():
        _lock_account(account_id)
        attempts = list(
            QuizAttempt.objects.select_for_update().filter(
                account_id=account_id,
                status__in=(QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED),
            )
        )
        if len(attempts) != expected_count:
            raise LearningCommandError(
                "learning.quiz_record_count_conflict.v1", "记录数量已变化，请重新确认。"
            )
        items = []
        for attempt in attempts:
            attempt.status = QuizAttemptStatus.DELETE_PENDING
            attempt.deletion_requested_at = current
            attempt.purge_after = current + DELETE_COOLING_PERIOD
            attempt.row_version += 1
            attempt.save(
                update_fields=(
                    "status",
                    "deletion_requested_at",
                    "purge_after",
                    "row_version",
                    "updated_at",
                )
            )
            items.append(
                QuizRecordBatchItem(attempt.id, "deleted", attempt.row_version, None)
            )
    return QuizRecordBatchResult(len(items), len(items), tuple(items))


__all__ = [
    "DELETE_COOLING_PERIOD",
    "MAX_RECORD_BATCH",
    "QuizRecordBatchItem",
    "QuizRecordBatchResult",
    "QuizRecordMutationResult",
    "WrongQuestionMutationResult",
    "delete_quiz_records",
    "delete_all_quiz_records",
    "purge_due_quiz_record",
    "quiz_record_delete_preflight",
    "request_quiz_record_deletion",
    "restore_quiz_record",
    "set_wrong_question_mastery",
]
