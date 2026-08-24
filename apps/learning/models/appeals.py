from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.learning.contracts import LearningAppealState


class LearningAppeal(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    document = models.ForeignKey(
        "learning.KnowledgeDocument",
        related_name="appeals",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    question_bank = models.ForeignKey(
        "learning.QuestionBank",
        related_name="appeals",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    appellant = models.ForeignKey(
        "accounts.Account",
        related_name="learning_appeals",
        on_delete=models.PROTECT,
    )
    target_row_version = models.PositiveBigIntegerField()
    reason_markdown = models.TextField()
    state = models.CharField(
        max_length=12,
        choices=LearningAppealState.choices,
        default=LearningAppealState.PENDING,
    )
    decision_markdown = models.TextField(null=True, blank=True)
    decided_by = models.ForeignKey(
        "accounts.Account",
        related_name="decided_learning_appeals",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_appeal"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("document",),
                condition=Q(
                    state=LearningAppealState.PENDING,
                    document__isnull=False,
                ),
                name="learning_appeal_one_pending_document",
            ),
            models.UniqueConstraint(
                fields=("question_bank",),
                condition=Q(
                    state=LearningAppealState.PENDING,
                    question_bank__isnull=False,
                ),
                name="learning_appeal_one_pending_bank",
            ),
            models.CheckConstraint(
                condition=(
                    Q(document__isnull=False, question_bank__isnull=True)
                    | Q(document__isnull=True, question_bank__isnull=False)
                ),
                name="learning_appeal_target_shape",
            ),
            models.CheckConstraint(
                condition=Q(state__in=LearningAppealState.values),
                name="learning_appeal_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(target_row_version__gte=1, row_version__gte=1),
                name="learning_appeal_versions_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=LearningAppealState.PENDING,
                        decision_markdown__isnull=True,
                        decided_by__isnull=True,
                        decided_at__isnull=True,
                        withdrawn_at__isnull=True,
                    )
                    | Q(
                        state__in=(
                            LearningAppealState.APPROVED,
                            LearningAppealState.REJECTED,
                        ),
                        decision_markdown__isnull=False,
                        decided_by__isnull=False,
                        decided_at__isnull=False,
                        withdrawn_at__isnull=True,
                    )
                    | Q(
                        state=LearningAppealState.WITHDRAWN,
                        decision_markdown__isnull=True,
                        decided_by__isnull=True,
                        decided_at__isnull=True,
                        withdrawn_at__isnull=False,
                    )
                ),
                name="learning_appeal_decision_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "created_at", "id"),
                name="learning_appeal_state_idx",
            )
        ]
