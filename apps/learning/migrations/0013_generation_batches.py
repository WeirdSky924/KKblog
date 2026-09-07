import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q

from apps.core.ids import new_uuid


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0012_question_bank_point_source_units"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestionBankGenerationBatch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=new_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("batch_number", models.PositiveSmallIntegerField()),
                ("source_unit_ids", models.JSONField(default=list, editable=False)),
                (
                    "source_unit_digests",
                    models.JSONField(default=list, editable=False),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("RUNNING", "Running"),
                            ("SUCCEEDED", "Succeeded"),
                        ],
                        default="PENDING",
                        editable=False,
                        max_length=10,
                    ),
                ),
                (
                    "attempt_count",
                    models.PositiveSmallIntegerField(default=0, editable=False),
                ),
                (
                    "latest_invocation_id",
                    models.CharField(
                        blank=True, editable=False, max_length=26, null=True
                    ),
                ),
                (
                    "publication",
                    models.JSONField(blank=True, editable=False, null=True),
                ),
                (
                    "publication_sha256",
                    models.CharField(
                        blank=True, default="", editable=False, max_length=64
                    ),
                ),
                (
                    "last_error_code",
                    models.CharField(
                        blank=True, default="", editable=False, max_length=96
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                (
                    "completed_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True, editable=False)),
                (
                    "series",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="generation_batches",
                        to="learning.questionbankseries",
                    ),
                ),
            ],
            options={
                "db_table": "learning_question_bank_generation_batch",
                "ordering": ("series_id", "batch_number"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("series", "batch_number"),
                        name="learning_generation_batch_series_number_unique",
                    ),
                    models.CheckConstraint(
                        condition=Q(
                            ("batch_number__gte", 1),
                            ("batch_number__lte", 4000),
                        ),
                        name="learning_generation_batch_number_range",
                    ),
                    models.CheckConstraint(
                        condition=Q(
                            ("state__in", ("PENDING", "RUNNING", "SUCCEEDED")),
                        ),
                        name="learning_generation_batch_state_valid",
                    ),
                    models.CheckConstraint(
                        condition=Q(("attempt_count__lte", 3)),
                        name="learning_generation_batch_attempt_range",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(
                                ("completed_at__isnull", True),
                                ("publication__isnull", True),
                                ("publication_sha256", ""),
                                ("state__in", ("PENDING", "RUNNING")),
                            )
                            | (
                                Q(
                                    ("completed_at__isnull", False),
                                    ("publication__isnull", False),
                                    ("state", "SUCCEEDED"),
                                )
                                & ~Q(("publication_sha256", ""))
                            )
                        ),
                        name="learning_generation_batch_result_shape",
                    ),
                    models.CheckConstraint(
                        condition=(
                            Q(("last_error_code", ""))
                            | Q(
                                (
                                    "last_error_code__regex",
                                    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$",
                                )
                            )
                        ),
                        name="learning_generation_batch_error_shape",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=("series", "state", "batch_number"),
                        name="learn_gen_batch_state_idx",
                    )
                ],
            },
        ),
    ]
