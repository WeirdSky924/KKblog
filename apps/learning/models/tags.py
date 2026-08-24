from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid


class QuestionBankTag(models.Model):
    class Source(models.TextChoices):
        REUSED = "REUSED", "Reused"
        AGENT = "AGENT", "Agent suggestion"
        OWNER = "OWNER", "Owner"
        ADMINISTRATOR = "ADMINISTRATOR", "Administrator"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RETIRED = "RETIRED", "Retired"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    normalized_name = models.CharField(max_length=80, unique=True)
    display_name = models.CharField(max_length=80)
    source = models.CharField(max_length=16, choices=Source.choices)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    usage_count = models.PositiveIntegerField(default=0)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_question_bank_tag"
        ordering = ("normalized_name", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(source__in=("REUSED", "AGENT", "OWNER", "ADMINISTRATOR")),
                name="learning_bank_tag_source_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("ACTIVE", "RETIRED")),
                name="learning_bank_tag_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_bank_tag_version_positive",
            ),
        ]
        indexes = [
            GinIndex(
                fields=("display_name",),
                name="learn_tag_display_trgm_idx",
                opclasses=("gin_trgm_ops",),
            )
        ]


class QuestionBankTagAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    series = models.ForeignKey(
        "learning.QuestionBankSeries",
        related_name="tag_assignments",
        on_delete=models.CASCADE,
    )
    tag = models.ForeignKey(
        QuestionBankTag,
        related_name="series_assignments",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "learning_question_bank_tag_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=("series", "tag"),
                name="learning_bank_series_tag_unique",
            )
        ]
