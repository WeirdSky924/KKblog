from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.learning.contracts import (
    DEFAULT_CONCURRENT_MODEL_RUNS,
    DEFAULT_DAILY_GENERATIONS,
    DEFAULT_DAILY_UPLOADS,
    DEFAULT_PENDING_REVIEWS,
    DEFAULT_UNPURGED_BANKS,
    MAX_CONCURRENT_MODEL_RUNS,
    MAX_DAILY_GENERATIONS,
    MAX_DAILY_UPLOADS,
    MAX_PENDING_REVIEWS,
    MAX_QUESTIONS_PER_VOLUME,
    MAX_UNPURGED_BANKS,
    MIN_CONCURRENT_MODEL_RUNS,
    MIN_DAILY_GENERATIONS,
    MIN_DAILY_UPLOADS,
    MIN_PENDING_REVIEWS,
    MIN_QUESTIONS_PER_VOLUME,
    MIN_UNPURGED_BANKS,
    LearningModelRunKind,
    LearningModelRunStatus,
)


def _range_or_null(field: str, minimum: int, maximum: int) -> Q:
    return Q(**{f"{field}__isnull": True}) | Q(
        **{f"{field}__gte": minimum, f"{field}__lte": maximum}
    )


class LearningQuotaPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    daily_uploads = models.PositiveSmallIntegerField(default=DEFAULT_DAILY_UPLOADS)
    pending_reviews = models.PositiveSmallIntegerField(default=DEFAULT_PENDING_REVIEWS)
    daily_generations = models.PositiveSmallIntegerField(
        default=DEFAULT_DAILY_GENERATIONS
    )
    concurrent_model_runs = models.PositiveSmallIntegerField(
        default=DEFAULT_CONCURRENT_MODEL_RUNS
    )
    unpurged_banks = models.PositiveIntegerField(default=DEFAULT_UNPURGED_BANKS)
    max_questions_per_volume = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_quota_policy"
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="learning_quota_singleton"),
            models.CheckConstraint(
                condition=Q(
                    daily_uploads__gte=MIN_DAILY_UPLOADS,
                    daily_uploads__lte=MAX_DAILY_UPLOADS,
                ),
                name="learning_quota_upload_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    pending_reviews__gte=MIN_PENDING_REVIEWS,
                    pending_reviews__lte=MAX_PENDING_REVIEWS,
                ),
                name="learning_quota_pending_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    daily_generations__gte=MIN_DAILY_GENERATIONS,
                    daily_generations__lte=MAX_DAILY_GENERATIONS,
                ),
                name="learning_quota_generation_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    concurrent_model_runs__gte=MIN_CONCURRENT_MODEL_RUNS,
                    concurrent_model_runs__lte=MAX_CONCURRENT_MODEL_RUNS,
                ),
                name="learning_quota_concurrent_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    unpurged_banks__gte=MIN_UNPURGED_BANKS,
                    unpurged_banks__lte=MAX_UNPURGED_BANKS,
                ),
                name="learning_quota_bank_range",
            ),
            models.CheckConstraint(
                condition=_range_or_null(
                    "max_questions_per_volume",
                    MIN_QUESTIONS_PER_VOLUME,
                    MAX_QUESTIONS_PER_VOLUME,
                ),
                name="learning_quota_question_limit_range",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_quota_version_positive",
            ),
        ]


class LearningAccountQuotaOverride(models.Model):
    account = models.OneToOneField(
        "accounts.Account",
        primary_key=True,
        related_name="learning_quota_override",
        on_delete=models.CASCADE,
    )
    daily_uploads = models.PositiveSmallIntegerField(null=True, blank=True)
    pending_reviews = models.PositiveSmallIntegerField(null=True, blank=True)
    daily_generations = models.PositiveSmallIntegerField(null=True, blank=True)
    concurrent_model_runs = models.PositiveSmallIntegerField(null=True, blank=True)
    unpurged_banks = models.PositiveIntegerField(null=True, blank=True)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_account_quota_override"
        constraints = [
            models.CheckConstraint(
                condition=_range_or_null(
                    "daily_uploads", MIN_DAILY_UPLOADS, MAX_DAILY_UPLOADS
                ),
                name="learning_account_upload_range",
            ),
            models.CheckConstraint(
                condition=_range_or_null(
                    "pending_reviews", MIN_PENDING_REVIEWS, MAX_PENDING_REVIEWS
                ),
                name="learning_account_pending_range",
            ),
            models.CheckConstraint(
                condition=_range_or_null(
                    "daily_generations",
                    MIN_DAILY_GENERATIONS,
                    MAX_DAILY_GENERATIONS,
                ),
                name="learning_account_generation_range",
            ),
            models.CheckConstraint(
                condition=_range_or_null(
                    "concurrent_model_runs",
                    MIN_CONCURRENT_MODEL_RUNS,
                    MAX_CONCURRENT_MODEL_RUNS,
                ),
                name="learning_account_concurrent_range",
            ),
            models.CheckConstraint(
                condition=_range_or_null(
                    "unpurged_banks", MIN_UNPURGED_BANKS, MAX_UNPURGED_BANKS
                ),
                name="learning_account_bank_range",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_account_quota_version_positive",
            ),
        ]


class LearningAccountQuotaState(models.Model):
    account = models.OneToOneField(
        "accounts.Account",
        primary_key=True,
        related_name="learning_quota_state",
        on_delete=models.CASCADE,
    )
    active_model_runs = models.PositiveSmallIntegerField(default=0)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_account_quota_state"
        constraints = [
            models.CheckConstraint(
                condition=Q(active_model_runs__lte=MAX_CONCURRENT_MODEL_RUNS),
                name="learning_account_active_runs_range",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_account_state_version_positive",
            ),
        ]


class LearningDailyUsage(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        related_name="learning_daily_usage",
        on_delete=models.CASCADE,
    )
    usage_date = models.DateField()
    uploads_created = models.PositiveSmallIntegerField(default=0)
    generations_accepted = models.PositiveSmallIntegerField(default=0)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_daily_usage"
        constraints = [
            models.UniqueConstraint(
                fields=("account", "usage_date"),
                name="learning_daily_usage_account_date_unique",
            ),
            models.CheckConstraint(
                condition=Q(uploads_created__lte=MAX_DAILY_UPLOADS),
                name="learning_daily_upload_range",
            ),
            models.CheckConstraint(
                condition=Q(generations_accepted__lte=MAX_DAILY_GENERATIONS),
                name="learning_daily_generation_range",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_daily_usage_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("usage_date", "account"),
                name="learning_daily_usage_date_idx",
            )
        ]


class LearningModelRunReservation(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    account = models.ForeignKey(
        "accounts.Account",
        related_name="learning_model_run_reservations",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(max_length=16, choices=LearningModelRunKind.choices)
    owner_ref = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(
        max_length=12,
        choices=LearningModelRunStatus.choices,
        default=LearningModelRunStatus.ACTIVE,
    )
    lease_expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_model_run_reservation"
        constraints = [
            models.UniqueConstraint(
                fields=("account", "kind", "owner_ref"),
                name="learning_model_run_owner_unique",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=LearningModelRunKind.values),
                name="learning_model_run_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=LearningModelRunStatus.values),
                name="learning_model_run_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=LearningModelRunStatus.ACTIVE, released_at__isnull=True)
                    | Q(
                        status__in=(
                            LearningModelRunStatus.RELEASED,
                            LearningModelRunStatus.EXPIRED,
                        ),
                        released_at__isnull=False,
                    )
                ),
                name="learning_model_run_release_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "lease_expires_at"),
                name="learning_model_run_lease_idx",
            )
        ]
