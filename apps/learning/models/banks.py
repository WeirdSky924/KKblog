from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.core.ids import new_uuid
from apps.learning.contracts import (
    LearningDeletionActor,
    QuestionBankCoverageState,
    QuestionBankSeriesState,
    QuestionBankVisibility,
)

_VISIBLE_STATES = (
    QuestionBankVisibility.PUBLISHED,
    QuestionBankVisibility.OWNER_HIDDEN,
    QuestionBankVisibility.ADMIN_HIDDEN,
    QuestionBankVisibility.DELETE_PENDING,
)
_PRE_DELETE_STATES = (
    QuestionBankVisibility.PUBLISHED,
    QuestionBankVisibility.OWNER_HIDDEN,
    QuestionBankVisibility.ADMIN_HIDDEN,
)


class QuestionBankSeries(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    owner = models.ForeignKey(
        "accounts.Account",
        related_name="question_bank_series",
        on_delete=models.PROTECT,
    )
    source_document = models.ForeignKey(
        "learning.KnowledgeDocument",
        related_name="question_bank_series",
        on_delete=models.PROTECT,
    )
    base_title = models.CharField(max_length=160)
    description = models.CharField(max_length=1_000, blank=True, default="")
    allowed_question_types = models.JSONField(default=list)
    max_questions_per_volume_snapshot = models.PositiveSmallIntegerField()
    input_content_sha256 = models.CharField(max_length=64)
    submission_idempotency_key = models.CharField(max_length=128)
    state = models.CharField(
        max_length=24,
        choices=QuestionBankSeriesState.choices,
        default=QuestionBankSeriesState.GENERATION_PENDING,
    )
    coverage_state = models.CharField(
        max_length=12,
        choices=QuestionBankCoverageState.choices,
        null=True,
        blank=True,
    )
    total_knowledge_points = models.PositiveIntegerField(default=0)
    covered_knowledge_points = models.PositiveIntegerField(default=0)
    omitted_knowledge_points = models.PositiveIntegerField(default=0)
    reserved_bank_slots = models.PositiveSmallIntegerField(default=1)
    safe_reason_code = models.CharField(max_length=96, blank=True, default="")
    safe_summary = models.CharField(max_length=500, null=True, blank=True)
    last_error_code = models.CharField(max_length=96, blank=True, default="")
    task_run_id = models.CharField(
        max_length=26,
        null=True,
        blank=True,
        editable=False,
    )
    latest_invocation_id = models.CharField(
        max_length=26,
        null=True,
        blank=True,
        editable=False,
    )
    generation_snapshot_invocation_id = models.CharField(
        max_length=26,
        null=True,
        blank=True,
        editable=False,
    )
    latest_learning_reservation_id = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0, editable=False)
    chunk_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        editable=False,
    )
    estimated_input_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
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
        db_table = "learning_question_bank_series"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "submission_idempotency_key"),
                name="learning_bank_series_owner_idem_unique",
            ),
            models.CheckConstraint(
                condition=Q(state__in=QuestionBankSeriesState.values),
                name="learning_bank_series_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    max_questions_per_volume_snapshot__gte=1,
                    max_questions_per_volume_snapshot__lte=2_000,
                ),
                name="learning_bank_series_limit_range",
            ),
            models.CheckConstraint(
                condition=Q(reserved_bank_slots__in=(1, 2)),
                name="learning_bank_series_slots_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_knowledge_points=F("covered_knowledge_points")
                    + F("omitted_knowledge_points")
                ),
                name="learning_bank_series_coverage_balance",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=QuestionBankSeriesState.PUBLISHED,
                        coverage_state__in=QuestionBankCoverageState.values,
                        total_knowledge_points__gte=1,
                        covered_knowledge_points__gte=1,
                    )
                    | (
                        ~Q(state=QuestionBankSeriesState.PUBLISHED)
                        & Q(coverage_state__isnull=True)
                    )
                ),
                name="learning_bank_series_publish_shape",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_bank_series_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(input_content_sha256__regex=r"^[0-9a-f]{64}$"),
                name="learning_bank_series_input_sha_shape",
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
                name="learning_bank_series_last_error_shape",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__lte=3),
                name="learning_bank_series_attempt_range",
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
                name="learning_bank_series_execution_shape",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(state=QuestionBankSeriesState.GENERATING)
                    | Q(generation_snapshot_invocation_id__isnull=False)
                ),
                name="learning_bank_series_snapshot_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(chunk_count__isnull=True, estimated_input_tokens__isnull=True)
                    | Q(
                        chunk_count__gte=1,
                        chunk_count__lte=128,
                        estimated_input_tokens__gte=1,
                    )
                ),
                name="learning_bank_series_input_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(dispatch_required=True, dispatched_at__isnull=True)
                    | Q(dispatch_required=False, dispatched_at__isnull=False)
                ),
                name="learning_bank_series_dispatch_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=QuestionBankSeriesState.GENERATION_PENDING,
                        started_at__isnull=True,
                        completed_at__isnull=True,
                        safe_reason_code="",
                        safe_summary__isnull=True,
                    )
                    | Q(
                        state=QuestionBankSeriesState.GENERATING,
                        started_at__isnull=False,
                        completed_at__isnull=True,
                        safe_reason_code="",
                        safe_summary__isnull=True,
                    )
                    | (
                        Q(
                            state__in=(
                                QuestionBankSeriesState.PUBLISHED,
                                QuestionBankSeriesState.GENERATION_FAILED,
                            ),
                            started_at__isnull=False,
                            completed_at__isnull=False,
                            safe_summary__isnull=False,
                        )
                        & ~Q(safe_reason_code="")
                    )
                    | Q(state=QuestionBankSeriesState.DELETED)
                ),
                name="learning_bank_series_runtime_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=QuestionBankSeriesState.GENERATION_FAILED,
                        failure_purge_after__isnull=False,
                    )
                    | (
                        ~Q(state=QuestionBankSeriesState.GENERATION_FAILED)
                        & Q(failure_purge_after__isnull=True)
                    )
                ),
                name="learning_bank_series_failure_purge_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("owner", "state", "-created_at", "id"),
                name="learn_bank_series_owner_idx",
            ),
            models.Index(
                fields=("state", "failure_purge_after", "id"),
                name="learn_bank_series_fail_idx",
            ),
            GinIndex(
                fields=("base_title",),
                name="learn_series_title_trgm_idx",
                opclasses=("gin_trgm_ops",),
            ),
            GinIndex(
                fields=("description",),
                name="learn_series_desc_trgm_idx",
                opclasses=("gin_trgm_ops",),
            ),
        ]


class QuestionBank(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    series = models.ForeignKey(
        QuestionBankSeries,
        related_name="banks",
        on_delete=models.PROTECT,
    )
    volume_number = models.PositiveSmallIntegerField()
    current_revision = models.ForeignKey(
        "learning.QuestionBankRevision",
        related_name="current_for_banks",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    visibility = models.CharField(
        max_length=16,
        choices=QuestionBankVisibility.choices,
        default=QuestionBankVisibility.CONFIGURING,
    )
    admin_lock_reason = models.CharField(max_length=96, blank=True, default="")
    pre_delete_visibility = models.CharField(
        max_length=16,
        choices=QuestionBankVisibility.choices,
        null=True,
        blank=True,
        editable=False,
    )
    deletion_requested_at = models.DateTimeField(null=True, blank=True, editable=False)
    deletion_actor = models.CharField(
        max_length=8,
        choices=LearningDeletionActor.choices,
        blank=True,
        default="",
        editable=False,
    )
    purge_after = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    first_published_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_attempt_count = models.PositiveBigIntegerField(default=0, editable=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_question_bank"
        ordering = ("series_id", "volume_number")
        constraints = [
            models.UniqueConstraint(
                fields=("series", "volume_number"),
                name="learning_bank_series_volume_unique",
            ),
            models.CheckConstraint(
                condition=Q(volume_number__in=(1, 2)),
                name="learning_bank_volume_valid",
            ),
            models.CheckConstraint(
                condition=Q(visibility__in=QuestionBankVisibility.values),
                name="learning_bank_visibility_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        visibility=QuestionBankVisibility.CONFIGURING,
                        current_revision__isnull=True,
                        first_published_at__isnull=True,
                    )
                    | Q(
                        visibility__in=_VISIBLE_STATES,
                        current_revision__isnull=False,
                        first_published_at__isnull=False,
                    )
                    | Q(visibility=QuestionBankVisibility.DELETED)
                ),
                name="learning_bank_revision_visibility_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        visibility=QuestionBankVisibility.DELETE_PENDING,
                        pre_delete_visibility__in=_PRE_DELETE_STATES,
                        deletion_requested_at__isnull=False,
                        purge_after__isnull=False,
                    )
                    | (
                        ~Q(visibility=QuestionBankVisibility.DELETE_PENDING)
                        & Q(
                            pre_delete_visibility__isnull=True,
                            deletion_requested_at__isnull=True,
                            purge_after__isnull=True,
                        )
                    )
                ),
                name="learning_bank_deletion_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        visibility=QuestionBankVisibility.DELETE_PENDING,
                        deletion_actor__in=LearningDeletionActor.values,
                    )
                    | (
                        ~Q(visibility=QuestionBankVisibility.DELETE_PENDING)
                        & Q(deletion_actor="")
                    )
                ),
                name="learning_bank_deletion_actor_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        visibility=QuestionBankVisibility.ADMIN_HIDDEN,
                    )
                    & ~Q(admin_lock_reason="")
                    | Q(
                        visibility=QuestionBankVisibility.DELETE_PENDING,
                        deletion_actor=LearningDeletionActor.ADMINISTRATOR,
                    )
                    & ~Q(admin_lock_reason="")
                    | Q(
                        visibility=QuestionBankVisibility.DELETE_PENDING,
                        pre_delete_visibility=QuestionBankVisibility.ADMIN_HIDDEN,
                    )
                    & ~Q(admin_lock_reason="")
                    | (
                        ~Q(
                            visibility__in=(
                                QuestionBankVisibility.ADMIN_HIDDEN,
                                QuestionBankVisibility.DELETE_PENDING,
                            )
                        )
                        & Q(admin_lock_reason="")
                    )
                    | Q(
                        visibility=QuestionBankVisibility.DELETE_PENDING,
                        deletion_actor=LearningDeletionActor.OWNER,
                        pre_delete_visibility__in=(
                            QuestionBankVisibility.PUBLISHED,
                            QuestionBankVisibility.OWNER_HIDDEN,
                        ),
                        admin_lock_reason="",
                    )
                    | Q(visibility=QuestionBankVisibility.DELETED)
                ),
                name="learning_bank_admin_lock_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        visibility=QuestionBankVisibility.DELETED,
                        deleted_at__isnull=False,
                    )
                    | (
                        ~Q(visibility=QuestionBankVisibility.DELETED)
                        & Q(deleted_at__isnull=True)
                    )
                ),
                name="learning_bank_deleted_at_shape",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_bank_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("visibility", "-first_published_at", "id"),
                name="learning_bank_public_idx",
            ),
            models.Index(
                fields=(
                    "visibility",
                    "-completed_attempt_count",
                    "-first_published_at",
                    "id",
                ),
                name="learn_bank_public_done_idx",
            ),
        ]


class QuestionBankRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    bank = models.ForeignKey(
        QuestionBank,
        related_name="revisions",
        on_delete=models.PROTECT,
    )
    sequence = models.PositiveIntegerField()
    question_count = models.PositiveIntegerField()
    single_choice_count = models.PositiveIntegerField(default=0)
    multiple_choice_count = models.PositiveIntegerField(default=0)
    true_false_count = models.PositiveIntegerField(default=0)
    short_answer_count = models.PositiveIntegerField(default=0)
    total_knowledge_points = models.PositiveIntegerField()
    covered_knowledge_points = models.PositiveIntegerField()
    omitted_knowledge_points = models.PositiveIntegerField()
    omitted_knowledge_point_ids = models.JSONField(default=list)
    schema_version = models.CharField(max_length=32, default="question-bank.v1")
    editor = models.ForeignKey(
        "accounts.Account",
        related_name="question_bank_revisions",
        on_delete=models.PROTECT,
    )
    reason = models.CharField(max_length=500)
    content_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "learning_question_bank_revision"
        ordering = ("bank_id", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("bank", "sequence"),
                name="learning_bank_revision_sequence_unique",
            ),
            models.UniqueConstraint(
                fields=("bank", "id"),
                name="learning_bank_revision_bank_id_unique",
            ),
            models.CheckConstraint(
                condition=Q(sequence__gte=1, question_count__gte=1),
                name="learning_bank_revision_counts_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    question_count=F("single_choice_count")
                    + F("multiple_choice_count")
                    + F("true_false_count")
                    + F("short_answer_count")
                ),
                name="learning_bank_revision_type_balance",
            ),
            models.CheckConstraint(
                condition=Q(
                    total_knowledge_points=F("covered_knowledge_points")
                    + F("omitted_knowledge_points")
                ),
                name="learning_bank_revision_coverage_balance",
            ),
            models.CheckConstraint(
                condition=Q(content_sha256__regex=r"^[0-9a-f]{64}$"),
                name="learning_bank_revision_sha_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("题库修订不可覆盖")
        return super().save(*args, **kwargs)


class QuestionBankKnowledgePoint(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    series = models.ForeignKey(
        QuestionBankSeries,
        related_name="knowledge_points",
        on_delete=models.PROTECT,
    )
    logical_id = models.CharField(max_length=64)
    title = models.CharField(max_length=300)
    importance = models.PositiveSmallIntegerField()
    source_unit_ids = models.JSONField(default=list)
    omitted = models.BooleanField(default=False)

    class Meta:
        db_table = "learning_question_bank_knowledge_point"
        ordering = ("-importance", "logical_id")
        constraints = [
            models.UniqueConstraint(
                fields=("series", "logical_id"),
                name="learning_bank_point_logical_unique",
            ),
            models.CheckConstraint(
                condition=Q(importance__gte=1, importance__lte=100),
                name="learning_bank_point_importance_range",
            ),
        ]
