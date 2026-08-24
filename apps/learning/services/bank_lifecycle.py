import re
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import is_active_account, is_administrator
from apps.core.events import enqueue_event
from apps.learning.contracts import (
    LEARNING_ADMIN_REASON_CODES,
    LearningCommandError,
    LearningDeletionActor,
    QuestionBankVisibility,
)
from apps.learning.events import QUESTION_BANK_ADMINISTRATION_CHANGED
from apps.learning.models import QuestionBank
from apps.operations.public import record_audit_entry

_REASON_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_TRACE_CODE = re.compile(r"^trc_[0-9a-hjkmnp-tv-z]{26}$")


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "题库时间不合法。")
    return current


def _candidate(actor_id, bank_id) -> tuple[QuestionBank, bool]:
    if not isinstance(actor_id, UUID) or not isinstance(bank_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    try:
        bank = QuestionBank.objects.select_related("series").get(pk=bank_id)
    except QuestionBank.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    administrator = is_administrator(actor_id)
    owner = bank.series.owner_id == actor_id and is_active_account(actor_id)
    if not owner and not administrator:
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    return bank, administrator


def _snapshot(bank: QuestionBank) -> dict[str, object]:
    return {
        "visibility": bank.visibility,
        "admin_lock_reason": bank.admin_lock_reason,
        "deletion_actor": bank.deletion_actor,
        "row_version": bank.row_version,
    }


def _admin_meta(*, trace_code, client_ip) -> tuple[str, str]:
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


def _record_admin_change(
    *,
    administrator_id: UUID,
    bank: QuestionBank,
    action: str,
    before: dict[str, object],
    trace_code,
    client_ip,
) -> None:
    trace, ip = _admin_meta(trace_code=trace_code, client_ip=client_ip)
    record_audit_entry(
        action=f"learning.bank.admin.{action.casefold()}",
        actor_id=administrator_id,
        target_id=str(bank.id),
        trace_code=trace,
        client_ip=ip,
        before=before,
        after=_snapshot(bank),
        summary=f"{action.title()} question bank",
    )
    enqueue_event(
        QUESTION_BANK_ADMINISTRATION_CHANGED,
        aggregate_type="question_bank",
        aggregate_id=str(bank.id),
        payload={
            "recipient_id": str(bank.series.owner_id),
            "action": action,
        },
    )


def set_question_bank_visibility(
    *,
    actor_id,
    bank_id,
    expected_version: int,
    target,
    reason_code: str = "",
    trace_code: str | None = None,
    client_ip: str | None = None,
) -> QuestionBank:
    candidate, administrator = _candidate(actor_id, bank_id)
    try:
        target_visibility = QuestionBankVisibility(target)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.bank_visibility_invalid.v1", "题库可见性不合法。"
        ) from None
    with transaction.atomic():
        bank = (
            QuestionBank.objects.select_for_update()
            .select_related("series")
            .get(pk=candidate.id)
        )
        if bank.row_version != expected_version:
            raise LearningCommandError(
                "learning.bank_conflict.v1", "题库已被其他操作修改。"
            )
        before = _snapshot(bank)
        if bank.visibility in {
            QuestionBankVisibility.CONFIGURING,
            QuestionBankVisibility.DELETE_PENDING,
            QuestionBankVisibility.DELETED,
        }:
            raise LearningCommandError(
                "learning.bank_visibility_invalid.v1", "题库当前不能修改可见性。"
            )
        if administrator:
            if target_visibility == QuestionBankVisibility.ADMIN_HIDDEN:
                if (
                    _REASON_CODE.fullmatch(reason_code or "") is None
                    or reason_code not in LEARNING_ADMIN_REASON_CODES
                ):
                    raise LearningCommandError(
                        "learning.bank_visibility_invalid.v1", "管理原因不合法。"
                    )
                bank.admin_lock_reason = reason_code
            elif target_visibility == QuestionBankVisibility.PUBLISHED:
                bank.admin_lock_reason = ""
            else:
                raise LearningCommandError(
                    "learning.bank_visibility_invalid.v1", "管理员目标状态不合法。"
                )
        else:
            if bank.visibility == QuestionBankVisibility.ADMIN_HIDDEN:
                raise LearningCommandError(
                    "learning.bank_admin_locked.v1", "题库已被管理员锁定。"
                )
            allowed = {
                (
                    QuestionBankVisibility.PUBLISHED,
                    QuestionBankVisibility.OWNER_HIDDEN,
                ),
                (
                    QuestionBankVisibility.OWNER_HIDDEN,
                    QuestionBankVisibility.PUBLISHED,
                ),
            }
            if (bank.visibility, target_visibility) not in allowed:
                raise LearningCommandError(
                    "learning.bank_visibility_invalid.v1", "题库目标状态不合法。"
                )
        bank.visibility = target_visibility
        bank.row_version += 1
        bank.save(
            update_fields=(
                "visibility",
                "admin_lock_reason",
                "row_version",
                "updated_at",
            )
        )
        if administrator:
            _record_admin_change(
                administrator_id=actor_id,
                bank=bank,
                action=(
                    "HIDE"
                    if target_visibility == QuestionBankVisibility.ADMIN_HIDDEN
                    else "RESTORE"
                ),
                before=before,
                trace_code=trace_code,
                client_ip=client_ip,
            )
    return bank


def delete_question_bank(
    *,
    actor_id,
    bank_id,
    expected_version: int,
    reason_code: str = "",
    trace_code: str | None = None,
    client_ip: str | None = None,
    now: datetime | None = None,
) -> QuestionBank:
    candidate, administrator = _candidate(actor_id, bank_id)
    current = _current_time(now)
    with transaction.atomic():
        bank = QuestionBank.objects.select_for_update().get(pk=candidate.id)
        if bank.row_version != expected_version or bank.visibility not in {
            QuestionBankVisibility.PUBLISHED,
            QuestionBankVisibility.OWNER_HIDDEN,
            QuestionBankVisibility.ADMIN_HIDDEN,
        }:
            raise LearningCommandError(
                "learning.bank_delete_conflict.v1", "题库当前不能删除。"
            )
        before = _snapshot(bank)
        if administrator:
            if (
                _REASON_CODE.fullmatch(reason_code or "") is None
                or reason_code not in LEARNING_ADMIN_REASON_CODES
            ):
                raise LearningCommandError(
                    "learning.bank_visibility_invalid.v1", "管理原因不合法。"
                )
            bank.admin_lock_reason = reason_code
            bank.deletion_actor = LearningDeletionActor.ADMINISTRATOR
        else:
            bank.deletion_actor = LearningDeletionActor.OWNER
        bank.pre_delete_visibility = bank.visibility
        bank.visibility = QuestionBankVisibility.DELETE_PENDING
        bank.deletion_requested_at = current
        bank.purge_after = current + timedelta(days=7)
        bank.row_version += 1
        bank.save()
        if administrator:
            _record_admin_change(
                administrator_id=actor_id,
                bank=bank,
                action="DELETE",
                before=before,
                trace_code=trace_code,
                client_ip=client_ip,
            )
    return bank


def restore_question_bank(
    *,
    actor_id,
    bank_id,
    expected_version: int,
    trace_code: str | None = None,
    client_ip: str | None = None,
    now: datetime | None = None,
) -> QuestionBank:
    candidate, administrator = _candidate(actor_id, bank_id)
    current = _current_time(now)
    with transaction.atomic():
        bank = QuestionBank.objects.select_for_update().get(pk=candidate.id)
        if (
            bank.row_version != expected_version
            or bank.visibility != QuestionBankVisibility.DELETE_PENDING
            or (
                bank.deletion_actor == LearningDeletionActor.ADMINISTRATOR
                and not administrator
            )
            or bank.purge_after is None
            or current >= bank.purge_after
        ):
            raise LearningCommandError(
                "learning.bank_restore_expired.v1", "题库已无法恢复。"
            )
        before = _snapshot(bank)
        bank.visibility = bank.pre_delete_visibility
        if bank.visibility != QuestionBankVisibility.ADMIN_HIDDEN:
            bank.admin_lock_reason = ""
        bank.pre_delete_visibility = None
        bank.deletion_requested_at = None
        bank.deletion_actor = ""
        bank.purge_after = None
        bank.row_version += 1
        bank.save()
        if administrator:
            _record_admin_change(
                administrator_id=actor_id,
                bank=bank,
                action="RESTORE",
                before=before,
                trace_code=trace_code,
                client_ip=client_ip,
            )
    return bank


__all__ = [
    "delete_question_bank",
    "restore_question_bank",
    "set_question_bank_visibility",
]
