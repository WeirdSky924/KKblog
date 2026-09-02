import pytest

from apps.learning.contracts import (
    DEFAULT_CONCURRENT_MODEL_RUNS,
    DEFAULT_DAILY_GENERATIONS,
    DEFAULT_DAILY_UPLOADS,
    DEFAULT_PENDING_REVIEWS,
    DEFAULT_UNPURGED_BANKS,
)
from apps.learning.models import LearningQuotaPolicy


@pytest.fixture(autouse=True)
def learning_quota_policy(db):
    LearningQuotaPolicy.objects.update_or_create(
        pk=1,
        defaults={
            "daily_uploads": DEFAULT_DAILY_UPLOADS,
            "pending_reviews": DEFAULT_PENDING_REVIEWS,
            "daily_generations": DEFAULT_DAILY_GENERATIONS,
            "concurrent_model_runs": DEFAULT_CONCURRENT_MODEL_RUNS,
            "unpurged_banks": DEFAULT_UNPURGED_BANKS,
            "row_version": 1,
        },
    )
