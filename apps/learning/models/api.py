from django.db import models
from django.db.models import F, Q

from apps.learning.contracts import (
    DEFAULT_API_DAILY_LIMIT,
    DEFAULT_API_MINUTE_LIMIT,
    MAX_API_DAILY_LIMIT,
    MAX_API_MINUTE_LIMIT,
    MIN_API_DAILY_LIMIT,
    MIN_API_MINUTE_LIMIT,
    QuestionBankApiCorsMode,
)


class QuestionBankApiConfiguration(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    cors_mode = models.CharField(
        max_length=16,
        choices=QuestionBankApiCorsMode.choices,
        default=QuestionBankApiCorsMode.ALLOWLIST,
    )
    cors_origins = models.JSONField(default=list)
    minute_limit = models.PositiveIntegerField(default=DEFAULT_API_MINUTE_LIMIT)
    daily_limit = models.PositiveIntegerField(default=DEFAULT_API_DAILY_LIMIT)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_question_bank_api_configuration"
        constraints = [
            models.CheckConstraint(
                condition=Q(id=1),
                name="learning_question_bank_api_singleton",
            ),
            models.CheckConstraint(
                condition=Q(cors_mode__in=QuestionBankApiCorsMode.values),
                name="learning_question_bank_api_cors_mode_valid",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_question_bank_api_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        minute_limit__gte=MIN_API_MINUTE_LIMIT,
                        minute_limit__lte=MAX_API_MINUTE_LIMIT,
                        daily_limit__gte=MIN_API_DAILY_LIMIT,
                        daily_limit__lte=MAX_API_DAILY_LIMIT,
                    )
                    & Q(daily_limit__gte=F("minute_limit"))
                ),
                name="learning_question_bank_api_limit_range",
            ),
        ]
