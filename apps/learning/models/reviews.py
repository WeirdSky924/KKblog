from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.learning.contracts import KnowledgeReviewRunState

_ACTIVE_STATES = (
    KnowledgeReviewRunState.PENDING,
    KnowledgeReviewRunState.RUNNING,
)
_TERMINAL_STATES = (
    KnowledgeReviewRunState.APPROVED,
    KnowledgeReviewRunState.REJECTED,
    KnowledgeReviewRunState.FAILED,
)
_FAILURE_STATES = (
    KnowledgeReviewRunState.REJECTED,
    KnowledgeReviewRunState.FAILED,
)


class KnowledgeReviewRun(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    document = models.ForeignKey(
        "learning.KnowledgeDocument",
        related_name="review_runs",
        on_delete=models.PROTECT,
    )
    sequence = models.PositiveIntegerField()
    state = models.CharField(
        max_length=16,
        choices=KnowledgeReviewRunState.choices,
        default=KnowledgeReviewRunState.PENDING,
    )
    input_content_sha256 = models.CharField(max_length=64, null=True, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    safe_reason_code = models.CharField(max_length=96, blank=True, default="")
    safe_summary = models.CharField(max_length=500, null=True, blank=True)
    risk_categories = models.JSONField(default=list)
    last_error_code = models.CharField(max_length=96, blank=True, default="")
    task_run_id = models.CharField(max_length=26, null=True, blank=True, editable=False)
    latest_invocation_id = models.CharField(
        max_length=26, null=True, blank=True, editable=False
    )
    latest_learning_reservation_id = models.UUIDField(
        null=True, blank=True, editable=False
    )
    attempt_count = models.PositiveSmallIntegerField(default=0, editable=False)
    chunk_count = models.PositiveSmallIntegerField(
        null=True, blank=True, editable=False
    )
    estimated_input_tokens = models.PositiveIntegerField(
        null=True, blank=True, editable=False
    )
    dispatch_required = models.BooleanField(default=True, editable=False)
    dispatch_attempted_at = models.DateTimeField(null=True, blank=True, editable=False)
    dispatched_at = models.DateTimeField(null=True, blank=True, editable=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    failure_purge_after = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_knowledge_review_run"
        ordering = ("document_id", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("document", "sequence"),
                name="learning_review_document_sequence_unique",
            ),
            models.UniqueConstraint(
                fields=("document",),
                condition=Q(state__in=_ACTIVE_STATES),
                name="learning_review_one_active_per_document",
            ),
            models.CheckConstraint(
                condition=Q(sequence__gte=1),
                name="learning_review_sequence_positive",
            ),
            models.CheckConstraint(
                condition=Q(state__in=KnowledgeReviewRunState.values),
                name="learning_review_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_review_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(last_error_code="")
                    | Q(
                        last_error_code__regex=(
                            r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+"
                            r"\.v[1-9][0-9]*$"
                        )
                    )
                ),
                name="learning_review_last_error_shape",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__lte=3),
                name="learning_review_attempt_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        attempt_count=0,
                        task_run_id__isnull=True,
                        latest_invocation_id__isnull=True,
                        latest_learning_reservation_id__isnull=True,
                    )
                    | Q(attempt_count__gte=1, task_run_id__isnull=False)
                ),
                name="learning_review_execution_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        chunk_count__isnull=True,
                        estimated_input_tokens__isnull=True,
                    )
                    | Q(
                        chunk_count__gte=1,
                        chunk_count__lte=128,
                        estimated_input_tokens__gte=1,
                    )
                ),
                name="learning_review_input_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(dispatch_required=True, dispatched_at__isnull=True)
                    | Q(dispatch_required=False, dispatched_at__isnull=False)
                ),
                name="learning_review_dispatch_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(input_content_sha256__isnull=True)
                    | Q(input_content_sha256__regex=r"^[0-9a-f]{64}$")
                ),
                name="learning_review_sha_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=KnowledgeReviewRunState.PENDING,
                        started_at__isnull=True,
                        completed_at__isnull=True,
                        safe_reason_code="",
                        safe_summary__isnull=True,
                    )
                    | Q(
                        state=KnowledgeReviewRunState.RUNNING,
                        started_at__isnull=False,
                        completed_at__isnull=True,
                        safe_reason_code="",
                        safe_summary__isnull=True,
                    )
                    | (
                        Q(
                            state__in=_TERMINAL_STATES,
                            started_at__isnull=False,
                            completed_at__isnull=False,
                        )
                        & ~Q(safe_reason_code="")
                        & (
                            Q(
                                input_content_sha256__isnull=False,
                                safe_summary__isnull=False,
                            )
                            | Q(
                                input_content_sha256__isnull=True,
                                safe_summary__isnull=True,
                            )
                        )
                    )
                    | (
                        Q(
                            state=KnowledgeReviewRunState.CANCELLED,
                            completed_at__isnull=False,
                        )
                        & ~Q(safe_reason_code="")
                    )
                ),
                name="learning_review_lifecycle_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state__in=_FAILURE_STATES, failure_purge_after__isnull=False)
                    | (
                        ~Q(state__in=_FAILURE_STATES)
                        & Q(failure_purge_after__isnull=True)
                    )
                ),
                name="learning_review_failure_purge_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "failure_purge_after", "id"),
                name="learning_review_failure_idx",
            )
        ]
