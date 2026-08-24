import re
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.public import can_upload_attachments, is_administrator
from apps.learning.contracts import (
    MAX_QUESTIONS_PER_VOLUME,
    MIN_QUESTIONS_PER_VOLUME,
    LearningCommandError,
    LearningModelRunKind,
    LearningModelRunStatus,
    LearningQuotaLimits,
    LearningQuotaOverride,
)
from apps.learning.models import (
    LearningAccountQuotaOverride,
    LearningDailyUsage,
    LearningModelRunReservation,
    LearningQuotaPolicy,
)
from apps.learning.policies import (
    effective_learning_quota,
    locked_account_quota_state,
    validate_quota_limits,
    validate_quota_override,
)
from apps.operations.public import record_audit_entry

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class LearningModelRunReservationResult:
    reservation_id: UUID
    status: str
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class DailyGenerationResetResult:
    usage_date: date
    account_count: int
    generations_reset: int


def _require_administrator(actor_id) -> UUID:
    if not isinstance(actor_id, UUID) or not is_administrator(actor_id):
        raise LearningCommandError(
            "learning.administrator_required.v1", "需要管理员权限。"
        )
    return actor_id


def _quota_snapshot(source) -> dict[str, int | None]:
    return {
        "daily_uploads": source.daily_uploads,
        "pending_reviews": source.pending_reviews,
        "daily_generations": source.daily_generations,
        "concurrent_model_runs": source.concurrent_model_runs,
        "unpurged_banks": source.unpurged_banks,
        "max_questions_per_volume": getattr(
            source,
            "max_questions_per_volume",
            None,
        ),
        "row_version": source.row_version,
    }


def _validate_question_limit(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MIN_QUESTIONS_PER_VOLUME <= value <= MAX_QUESTIONS_PER_VOLUME
    ):
        raise LearningCommandError(
            "learning.question_limit_invalid.v1",
            "单卷题数上限不合法。",
        )
    return value


def configure_question_generation_limit(
    *,
    actor_id,
    expected_version: int,
    max_questions_per_volume: int,
    trace_code: str,
    client_ip: str,
) -> LearningQuotaPolicy:
    actor = _require_administrator(actor_id)
    max_questions_per_volume = _validate_question_limit(max_questions_per_volume)
    with transaction.atomic():
        try:
            policy = LearningQuotaPolicy.objects.select_for_update().get(pk=1)
        except LearningQuotaPolicy.DoesNotExist:
            raise LearningCommandError(
                "learning.quota_unavailable.v1", "业务配额暂不可用。"
            ) from None
        if policy.row_version != expected_version:
            raise LearningCommandError(
                "learning.quota_conflict.v1", "业务配额已被其他操作修改。"
            )
        before = _quota_snapshot(policy)
        policy.max_questions_per_volume = max_questions_per_volume
        policy.row_version += 1
        policy.save(
            update_fields=(
                "max_questions_per_volume",
                "row_version",
                "updated_at",
            )
        )
        record_audit_entry(
            action="learning.question_limit.update",
            actor_id=actor,
            target_id="site",
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_quota_snapshot(policy),
            summary="Update question generation limit",
        )
    return policy


def configure_site_quota_policy(
    *,
    actor_id,
    expected_version: int,
    limits: LearningQuotaLimits,
    trace_code: str,
    client_ip: str,
    max_questions_per_volume: int | None = None,
) -> LearningQuotaPolicy:
    actor = _require_administrator(actor_id)
    validated = validate_quota_limits(limits)
    if max_questions_per_volume is not None:
        max_questions_per_volume = _validate_question_limit(max_questions_per_volume)
    with transaction.atomic():
        try:
            policy = LearningQuotaPolicy.objects.select_for_update().get(pk=1)
        except LearningQuotaPolicy.DoesNotExist:
            raise LearningCommandError(
                "learning.quota_unavailable.v1", "业务配额暂不可用。"
            ) from None
        if policy.row_version != expected_version:
            raise LearningCommandError(
                "learning.quota_conflict.v1", "业务配额已被其他操作修改。"
            )
        before = _quota_snapshot(policy)
        for field in validated.__dataclass_fields__:
            setattr(policy, field, getattr(validated, field))
        if max_questions_per_volume is not None:
            policy.max_questions_per_volume = max_questions_per_volume
        policy.row_version += 1
        policy.save()
        record_audit_entry(
            action="learning.quota.site.update",
            actor_id=actor,
            target_id="site",
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_quota_snapshot(policy),
            summary="Update learning site quota",
        )
    return policy


def reset_daily_generation_usage(
    *,
    actor_id,
    trace_code: str,
    client_ip: str,
    now: datetime | None = None,
) -> DailyGenerationResetResult:
    actor = _require_administrator(actor_id)
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError(
            "learning.time_invalid.v1", "生成计数重置时间不合法。"
        )
    usage_date = timezone.localdate(current)
    with transaction.atomic():
        rows = list(
            LearningDailyUsage.objects.select_for_update()
            .filter(usage_date=usage_date, generations_accepted__gt=0)
            .values_list("id", "generations_accepted")
        )
        account_count = len(rows)
        generations_reset = sum(value for _row_id, value in rows)
        if rows:
            LearningDailyUsage.objects.filter(
                id__in=[row_id for row_id, _value in rows]
            ).update(
                generations_accepted=0,
                row_version=F("row_version") + 1,
                updated_at=current,
            )
        record_audit_entry(
            action="learning.quota.daily_generation.reset",
            actor_id=actor,
            target_id="site",
            trace_code=trace_code,
            client_ip=client_ip,
            before={
                "usage_date": usage_date.isoformat(),
                "account_count": account_count,
                "generations_reset": generations_reset,
            },
            after={
                "usage_date": usage_date.isoformat(),
                "account_count": account_count,
                "generations_reset": 0,
            },
            summary="Reset daily learning generation usage",
        )
    return DailyGenerationResetResult(
        usage_date=usage_date,
        account_count=account_count,
        generations_reset=generations_reset,
    )


def configure_account_quota_override(
    *,
    actor_id,
    account_id,
    expected_version: int,
    limits: LearningQuotaOverride,
    trace_code: str,
    client_ip: str,
) -> LearningAccountQuotaOverride:
    actor = _require_administrator(actor_id)
    if not isinstance(account_id, UUID) or not can_upload_attachments(account_id):
        raise LearningCommandError(
            "learning.attachment_capability_required.v1",
            "目标账户当前没有附件能力。",
        )
    validated = validate_quota_override(limits)
    with transaction.atomic():
        current = (
            LearningAccountQuotaOverride.objects.select_for_update()
            .filter(account_id=account_id)
            .first()
        )
        if current is None:
            if expected_version != 0:
                raise LearningCommandError(
                    "learning.quota_conflict.v1", "账户业务配额已发生变化。"
                )
            current = LearningAccountQuotaOverride(account_id=account_id)
            before = {}
        else:
            if current.row_version != expected_version:
                raise LearningCommandError(
                    "learning.quota_conflict.v1", "账户业务配额已发生变化。"
                )
            before = _quota_snapshot(current)
            current.row_version += 1
        for field in validated.__dataclass_fields__:
            setattr(current, field, getattr(validated, field))
        current.save()
        record_audit_entry(
            action="learning.quota.account.update",
            actor_id=actor,
            target_id=str(account_id),
            trace_code=trace_code,
            client_ip=client_ip,
            before=before,
            after=_quota_snapshot(current),
            summary="Update learning account quota",
        )
    return current


def _reservation_result(
    reservation: LearningModelRunReservation,
) -> LearningModelRunReservationResult:
    return LearningModelRunReservationResult(
        reservation_id=reservation.id,
        status=reservation.status,
        lease_expires_at=reservation.lease_expires_at,
    )


def _recover_expired_model_runs(*, account_id: UUID, now: datetime) -> None:
    with transaction.atomic():
        state = locked_account_quota_state(account_id)
        expired_ids = tuple(
            LearningModelRunReservation.objects.select_for_update()
            .filter(
                account_id=account_id,
                status=LearningModelRunStatus.ACTIVE,
                lease_expires_at__lte=now,
            )
            .values_list("id", flat=True)
        )
        if expired_ids:
            LearningModelRunReservation.objects.filter(id__in=expired_ids).update(
                status=LearningModelRunStatus.EXPIRED,
                released_at=now,
            )
        active_count = LearningModelRunReservation.objects.filter(
            account_id=account_id,
            status=LearningModelRunStatus.ACTIVE,
        ).count()
        if expired_ids or state.active_model_runs != active_count:
            state.active_model_runs = active_count
            state.row_version += 1
            state.save(update_fields=("active_model_runs", "row_version", "updated_at"))


def reserve_learning_model_run(
    *,
    account_id,
    kind,
    owner_ref: str,
    idempotency_key: str,
    lease_expires_at: datetime,
    now: datetime | None = None,
) -> LearningModelRunReservationResult:
    current = now or timezone.now()
    if (
        not isinstance(account_id, UUID)
        or not can_upload_attachments(account_id)
        or not timezone.is_aware(current)
        or not timezone.is_aware(lease_expires_at)
        or lease_expires_at <= current
        or not isinstance(owner_ref, str)
        or not 1 <= len(owner_ref) <= 64
        or _IDEMPOTENCY_KEY.fullmatch(idempotency_key or "") is None
    ):
        raise LearningCommandError(
            "learning.reservation_invalid.v1", "模型任务预留信息不合法。"
        )
    try:
        normalized_kind = LearningModelRunKind(kind)
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.reservation_invalid.v1", "模型任务用途不合法。"
        ) from None
    existing = LearningModelRunReservation.objects.filter(
        idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        if (
            existing.account_id != account_id
            or existing.kind != normalized_kind
            or existing.owner_ref != owner_ref
        ):
            raise LearningCommandError(
                "learning.idempotency_conflict.v1",
                "相同幂等标识已用于其他模型任务。",
            )
        return _reservation_result(existing)

    _recover_expired_model_runs(account_id=account_id, now=current)
    with transaction.atomic():
        state = locked_account_quota_state(account_id)
        active_count = LearningModelRunReservation.objects.filter(
            account_id=account_id,
            status=LearningModelRunStatus.ACTIVE,
        ).count()
        limits = effective_learning_quota(account_id)
        if active_count >= limits.concurrent_model_runs:
            raise LearningCommandError(
                "learning.concurrent_quota_exhausted.v1",
                "当前模型任务并发额度已用完。",
            )
        try:
            reservation = LearningModelRunReservation.objects.create(
                account_id=account_id,
                kind=normalized_kind,
                owner_ref=owner_ref,
                idempotency_key=idempotency_key,
                lease_expires_at=lease_expires_at,
            )
        except IntegrityError as exc:
            raise LearningCommandError(
                "learning.reservation_conflict.v1", "模型任务已经预留。"
            ) from exc
        state.active_model_runs = active_count + 1
        state.row_version += 1
        state.save(update_fields=("active_model_runs", "row_version", "updated_at"))
    return _reservation_result(reservation)


def release_learning_model_run(*, reservation_id) -> LearningModelRunReservationResult:
    try:
        candidate = LearningModelRunReservation.objects.get(pk=reservation_id)
    except (LearningModelRunReservation.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.reservation_not_found.v1", "模型任务预留不存在。"
        ) from None
    with transaction.atomic():
        state = locked_account_quota_state(candidate.account_id)
        reservation = LearningModelRunReservation.objects.select_for_update().get(
            pk=candidate.id
        )
        if reservation.status != LearningModelRunStatus.ACTIVE:
            return _reservation_result(reservation)
        reservation.status = LearningModelRunStatus.RELEASED
        reservation.released_at = timezone.now()
        reservation.save(update_fields=("status", "released_at", "updated_at"))
        state.active_model_runs = LearningModelRunReservation.objects.filter(
            account_id=reservation.account_id,
            status=LearningModelRunStatus.ACTIVE,
        ).count()
        state.row_version += 1
        state.save(update_fields=("active_model_runs", "row_version", "updated_at"))
    return _reservation_result(reservation)
