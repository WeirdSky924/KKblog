from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid


class QuestionBankGenerationBatch(models.Model):
    """Durable result for one deterministic source batch of a generation run.

    The provider response is stored only after the shared output harness has
    validated it.  Keeping this checkpoint separate from ``QuestionBankSeries``
    lets a task retry resume at the first unfinished batch without publishing
    an incomplete question bank.
    """

    class State(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    series = models.ForeignKey(
        "learning.QuestionBankSeries",
        related_name="generation_batches",
        on_delete=models.CASCADE,
    )
    batch_number = models.PositiveSmallIntegerField()
    source_unit_ids = models.JSONField(default=list, editable=False)
    source_unit_digests = models.JSONField(default=list, editable=False)
    state = models.CharField(
        max_length=10,
        choices=State.choices,
        default=State.PENDING,
        editable=False,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0, editable=False)
    latest_invocation_id = models.CharField(
        max_length=26,
        null=True,
        blank=True,
        editable=False,
    )
    publication = models.JSONField(null=True, blank=True, editable=False)
    publication_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
    )
    last_error_code = models.CharField(
        max_length=96,
        blank=True,
        default="",
        editable=False,
    )
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_question_bank_generation_batch"
        ordering = ("series_id", "batch_number")
        constraints = [
            models.UniqueConstraint(
                fields=("series", "batch_number"),
                name="learning_generation_batch_series_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(batch_number__gte=1, batch_number__lte=4_000),
                name="learning_generation_batch_number_range",
            ),
            models.CheckConstraint(
                condition=Q(state__in=("PENDING", "RUNNING", "SUCCEEDED")),
                name="learning_generation_batch_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__lte=3),
                name="learning_generation_batch_attempt_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state__in=("PENDING", "RUNNING"),
                        publication__isnull=True,
                        publication_sha256="",
                        completed_at__isnull=True,
                    )
                    | (
                        Q(
                            state="SUCCEEDED",
                            publication__isnull=False,
                            completed_at__isnull=False,
                        )
                        & ~Q(publication_sha256="")
                    )
                ),
                name="learning_generation_batch_result_shape",
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
                name="learning_generation_batch_error_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("series", "state", "batch_number"),
                name="learn_gen_batch_state_idx",
            ),
        ]
