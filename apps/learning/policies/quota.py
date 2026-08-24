from datetime import date
from uuid import UUID

from apps.learning.contracts import (
    MAX_CONCURRENT_MODEL_RUNS,
    MAX_DAILY_GENERATIONS,
    MAX_DAILY_UPLOADS,
    MAX_PENDING_REVIEWS,
    MAX_UNPURGED_BANKS,
    MIN_CONCURRENT_MODEL_RUNS,
    MIN_DAILY_GENERATIONS,
    MIN_DAILY_UPLOADS,
    MIN_PENDING_REVIEWS,
    MIN_UNPURGED_BANKS,
    LearningCommandError,
    LearningQuotaLimits,
    LearningQuotaOverride,
)
from apps.learning.models import (
    LearningAccountQuotaOverride,
    LearningAccountQuotaState,
    LearningDailyUsage,
    LearningQuotaPolicy,
)

_RANGES = {
    "daily_uploads": (MIN_DAILY_UPLOADS, MAX_DAILY_UPLOADS),
    "pending_reviews": (MIN_PENDING_REVIEWS, MAX_PENDING_REVIEWS),
    "daily_generations": (MIN_DAILY_GENERATIONS, MAX_DAILY_GENERATIONS),
    "concurrent_model_runs": (
        MIN_CONCURRENT_MODEL_RUNS,
        MAX_CONCURRENT_MODEL_RUNS,
    ),
    "unpurged_banks": (MIN_UNPURGED_BANKS, MAX_UNPURGED_BANKS),
}


def _valid_integer(value, *, minimum: int, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def validate_quota_limits(limits: LearningQuotaLimits) -> LearningQuotaLimits:
    if not isinstance(limits, LearningQuotaLimits) or any(
        not _valid_integer(
            getattr(limits, field),
            minimum=minimum,
            maximum=maximum,
        )
        for field, (minimum, maximum) in _RANGES.items()
    ):
        raise LearningCommandError(
            "learning.quota_invalid.v1", "业务配额超出允许范围。"
        )
    return limits


def validate_quota_override(
    limits: LearningQuotaOverride,
) -> LearningQuotaOverride:
    if not isinstance(limits, LearningQuotaOverride) or any(
        value is not None
        and not _valid_integer(value, minimum=minimum, maximum=maximum)
        for field, (minimum, maximum) in _RANGES.items()
        if (value := getattr(limits, field)) is not None
    ):
        raise LearningCommandError(
            "learning.quota_invalid.v1", "账户业务配额超出允许范围。"
        )
    return limits


def effective_learning_quota(account_id: UUID) -> LearningQuotaLimits:
    if not isinstance(account_id, UUID):
        raise LearningCommandError(
            "learning.account_not_found.v1", "账户不存在或不可用。"
        )
    try:
        policy = LearningQuotaPolicy.objects.get(pk=1)
    except LearningQuotaPolicy.DoesNotExist:
        raise LearningCommandError(
            "learning.quota_unavailable.v1", "业务配额暂不可用。"
        ) from None
    override = LearningAccountQuotaOverride.objects.filter(
        account_id=account_id
    ).first()
    return LearningQuotaLimits(
        **{
            field: (
                getattr(override, field)
                if override is not None and getattr(override, field) is not None
                else getattr(policy, field)
            )
            for field in _RANGES
        }
    )


def locked_account_quota_state(account_id: UUID) -> LearningAccountQuotaState:
    LearningAccountQuotaState.objects.get_or_create(account_id=account_id)
    return LearningAccountQuotaState.objects.select_for_update().get(
        account_id=account_id
    )


def locked_daily_usage(
    account_id: UUID,
    usage_date: date,
) -> LearningDailyUsage:
    LearningDailyUsage.objects.get_or_create(
        account_id=account_id,
        usage_date=usage_date,
    )
    return LearningDailyUsage.objects.select_for_update().get(
        account_id=account_id,
        usage_date=usage_date,
    )
