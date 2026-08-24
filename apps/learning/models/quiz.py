import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.learning.contracts import (
    QUIZ_DURATION_OPTIONS,
    QuestionType,
    QuizAttemptSource,
    QuizAttemptStatus,
    QuizMasteryStatus,
    QuizSelfAssessment,
)


class QuizAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    bank = models.ForeignKey(
        "learning.QuestionBank",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quiz_attempts",
    )
    revision = models.ForeignKey(
        "learning.QuestionBankRevision",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quiz_attempts",
    )
    source = models.CharField(max_length=20, choices=QuizAttemptSource.choices)
    bank_id_snapshot = models.UUIDField()
    series_id_snapshot = models.UUIDField()
    revision_id_snapshot = models.UUIDField()
    owner_id_snapshot = models.UUIDField(null=True, blank=True)
    bank_title = models.CharField(max_length=160)
    owner_display_name = models.CharField(max_length=254)
    selected_question_types = models.JSONField(default=list)
    question_count = models.PositiveIntegerField()
    timed = models.BooleanField(default=False)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    random_questions = models.BooleanField(default=True)
    random_options = models.BooleanField(default=True)
    question_order = models.JSONField(default=list)
    option_orders = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=QuizAttemptStatus.choices,
        default=QuizAttemptStatus.IN_PROGRESS,
    )
    objective_score = models.PositiveIntegerField(null=True, blank=True)
    objective_total = models.PositiveIntegerField(null=True, blank=True)
    short_answer_mastered = models.PositiveIntegerField(null=True, blank=True)
    short_answer_total = models.PositiveIntegerField(null=True, blank=True)
    actual_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    submit_request_id = models.CharField(max_length=128, blank=True, default="")
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    started_at = models.DateTimeField(default=timezone.now, editable=False)
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deletion_requested_at = models.DateTimeField(null=True, blank=True, editable=False)
    purge_after = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learning_quiz_attempt"
        constraints = [
            models.CheckConstraint(
                condition=Q(question_count__gte=1),
                name="learning_quiz_attempt_question_count_positive",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_quiz_attempt_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(source__in=QuizAttemptSource.values),
                name="learning_quiz_attempt_source_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=QuizAttemptStatus.values),
                name="learning_quiz_attempt_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        timed=False,
                        duration_minutes__isnull=True,
                        deadline_at__isnull=True,
                    )
                    | Q(
                        timed=True,
                        duration_minutes__in=QUIZ_DURATION_OPTIONS,
                        deadline_at__isnull=False,
                    )
                ),
                name="learning_quiz_attempt_timer_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=QuizAttemptStatus.IN_PROGRESS, submitted_at__isnull=True)
                    | Q(status=QuizAttemptStatus.SUBMITTED, submitted_at__isnull=False)
                    | Q(
                        status=QuizAttemptStatus.DELETE_PENDING,
                        deletion_requested_at__isnull=False,
                        purge_after__isnull=False,
                    )
                    | Q(
                        status=QuizAttemptStatus.DELETED,
                        deleted_at__isnull=False,
                    )
                ),
                name="learning_quiz_attempt_status_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=QuizAttemptStatus.DELETE_PENDING,
                        deletion_requested_at__isnull=False,
                        purge_after__isnull=False,
                    )
                    | (
                        ~Q(status=QuizAttemptStatus.DELETE_PENDING)
                        & Q(
                            deletion_requested_at__isnull=True,
                            purge_after__isnull=True,
                        )
                    )
                ),
                name="learning_quiz_attempt_deletion_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=QuizAttemptStatus.IN_PROGRESS,
                        objective_score__isnull=True,
                        objective_total__isnull=True,
                        short_answer_mastered__isnull=True,
                        short_answer_total__isnull=True,
                        actual_duration_seconds__isnull=True,
                    )
                    | Q(
                        status=QuizAttemptStatus.SUBMITTED,
                        objective_score__isnull=False,
                        objective_total__isnull=False,
                        short_answer_mastered__isnull=False,
                        short_answer_total__isnull=False,
                        actual_duration_seconds__isnull=False,
                    )
                    | Q(
                        status__in=(
                            QuizAttemptStatus.DELETE_PENDING,
                            QuizAttemptStatus.DELETED,
                        )
                    )
                ),
                name="learning_quiz_attempt_result_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account", "status", "-started_at", "id"),
                name="learn_quiz_attempt_account_idx",
            ),
            models.Index(
                fields=("status", "purge_after", "id"),
                name="learn_quiz_attempt_purge_idx",
            ),
        ]


class QuizResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="responses"
    )
    question = models.ForeignKey(
        "learning.Question",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quiz_responses",
    )
    logical_id = models.CharField(max_length=64)
    ordinal = models.PositiveIntegerField()
    question_type = models.CharField(max_length=24, choices=QuestionType.choices)
    stem_markdown = models.TextField()
    options = models.JSONField(default=list)
    correct_option_ids = models.JSONField(default=list)
    boolean_answer = models.BooleanField(null=True, blank=True)
    reference_answer = models.TextField(blank=True, default="")
    scoring_points = models.JSONField(default=list)
    explanation_markdown = models.TextField()
    answer = models.JSONField(null=True, blank=True)
    self_assessment = models.CharField(
        max_length=16,
        choices=QuizSelfAssessment.choices,
        null=True,
        blank=True,
    )
    is_correct = models.BooleanField(null=True, blank=True, editable=False)
    score = models.PositiveIntegerField(null=True, blank=True, editable=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    last_save_request_id = models.CharField(max_length=128, blank=True, default="")
    assessment_request_id = models.CharField(max_length=128, blank=True, default="")
    saved_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "learning_quiz_response"
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "logical_id"),
                name="learning_quiz_response_attempt_logical_unique",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_quiz_response_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(question_type__in=QuestionType.values),
                name="learning_quiz_response_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        submitted_at__isnull=True,
                        is_correct__isnull=True,
                        score__isnull=True,
                    )
                    | Q(
                        submitted_at__isnull=False,
                        question_type=QuestionType.SHORT_ANSWER,
                        is_correct__isnull=True,
                        score__isnull=True,
                    )
                    | Q(
                        submitted_at__isnull=False,
                        question_type__in=(
                            QuestionType.SINGLE_CHOICE,
                            QuestionType.MULTIPLE_CHOICE,
                            QuestionType.TRUE_FALSE,
                        ),
                        is_correct__isnull=False,
                        score__isnull=False,
                    )
                ),
                name="learning_quiz_response_result_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("attempt", "ordinal", "id"),
                name="learn_quiz_response_order_idx",
            )
        ]


class WrongQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    bank = models.ForeignKey(
        "learning.QuestionBank", null=True, blank=True, on_delete=models.SET_NULL
    )
    question = models.ForeignKey(
        "learning.Question", null=True, blank=True, on_delete=models.SET_NULL
    )
    source_key = models.CharField(max_length=160)
    bank_title = models.CharField(max_length=160)
    owner_display_name = models.CharField(max_length=254)
    logical_id = models.CharField(max_length=64)
    question_type = models.CharField(max_length=24, choices=QuestionType.choices)
    stem_markdown = models.TextField()
    options = models.JSONField(default=list)
    correct_option_ids = models.JSONField(default=list)
    boolean_answer = models.BooleanField(null=True, blank=True)
    reference_answer = models.TextField(blank=True, default="")
    scoring_points = models.JSONField(default=list)
    explanation_markdown = models.TextField()
    first_wrong_at = models.DateTimeField()
    last_wrong_at = models.DateTimeField()
    wrong_count = models.PositiveIntegerField(default=1)
    correct_count = models.PositiveIntegerField(default=0)
    last_correct_at = models.DateTimeField(null=True, blank=True)
    mastery_status = models.CharField(
        max_length=16,
        choices=QuizMasteryStatus.choices,
        default=QuizMasteryStatus.TO_REVIEW,
    )
    status_changed_at = models.DateTimeField()
    row_version = models.PositiveBigIntegerField(default=1, editable=False)

    class Meta:
        db_table = "learning_wrong_question"
        constraints = [
            models.UniqueConstraint(
                fields=("account", "source_key"),
                name="learning_wrong_question_account_source_unique",
            ),
            models.CheckConstraint(
                condition=Q(wrong_count__gte=1, correct_count__gte=0),
                name="learning_wrong_question_counts_valid",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_wrong_question_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(mastery_status__in=QuizMasteryStatus.values),
                name="learning_wrong_question_mastery_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account", "mastery_status", "bank", "id"),
                name="learn_wrong_account_state_idx",
            )
        ]
