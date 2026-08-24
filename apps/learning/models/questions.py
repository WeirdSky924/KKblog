from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.learning.contracts import QuestionType


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    revision = models.ForeignKey(
        "learning.QuestionBankRevision",
        related_name="questions",
        on_delete=models.PROTECT,
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
    knowledge_point_ids = models.JSONField(default=list)
    validation_sha256 = models.CharField(max_length=64)

    class Meta:
        db_table = "learning_question"
        ordering = ("revision_id", "ordinal")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "logical_id"),
                name="learning_question_revision_logical_unique",
            ),
            models.UniqueConstraint(
                fields=("revision", "ordinal"),
                name="learning_question_revision_ordinal_unique",
            ),
            models.CheckConstraint(
                condition=Q(ordinal__gte=1),
                name="learning_question_ordinal_positive",
            ),
            models.CheckConstraint(
                condition=Q(question_type__in=QuestionType.values),
                name="learning_question_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        question_type__in=(
                            QuestionType.SINGLE_CHOICE,
                            QuestionType.MULTIPLE_CHOICE,
                        ),
                        boolean_answer__isnull=True,
                        reference_answer="",
                    )
                    | Q(
                        question_type=QuestionType.TRUE_FALSE,
                        options=[],
                        correct_option_ids=[],
                        boolean_answer__isnull=False,
                        reference_answer="",
                        scoring_points=[],
                    )
                    | (
                        Q(
                            question_type=QuestionType.SHORT_ANSWER,
                            options=[],
                            correct_option_ids=[],
                            boolean_answer__isnull=True,
                        )
                        & ~Q(reference_answer="")
                    )
                ),
                name="learning_question_answer_shape",
            ),
            models.CheckConstraint(
                condition=Q(validation_sha256__regex=r"^[0-9a-f]{64}$"),
                name="learning_question_sha_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("题目历史不可覆盖")
        return super().save(*args, **kwargs)
