import django.db.models.deletion
from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_audit_entry")]

    operations = [
        migrations.CreateModel(
            name="RuntimeError",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=apps.core.ids.new_ulid,
                        editable=False,
                        max_length=26,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "fingerprint",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                ("error_code", models.CharField(editable=False, max_length=96)),
                ("exception_type", models.CharField(editable=False, max_length=192)),
                ("safe_summary", models.CharField(editable=False, max_length=255)),
                ("safe_traceback", models.TextField(editable=False)),
                ("safe_context", models.JSONField(default=dict, editable=False)),
                ("latest_trace_code", models.CharField(editable=False, max_length=30)),
                (
                    "occurrence_count",
                    models.PositiveIntegerField(default=1, editable=False),
                ),
                ("first_seen_at", models.DateTimeField(editable=False)),
                ("last_seen_at", models.DateTimeField(editable=False)),
            ],
            options={
                "db_table": "operations_runtime_error",
                "ordering": ("-last_seen_at", "-id"),
                "indexes": [
                    models.Index(
                        fields=["error_code", "last_seen_at"],
                        name="runtime_error_code_idx",
                    ),
                    models.Index(
                        fields=["last_seen_at"], name="runtime_error_seen_idx"
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("occurrence_count__gte", 1)),
                        name="operations_runtime_error_count_positive",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="RuntimeErrorOccurrence",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=apps.core.ids.new_ulid,
                        editable=False,
                        max_length=26,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "trace_code",
                    models.CharField(editable=False, max_length=30),
                ),
                ("safe_context", models.JSONField(default=dict, editable=False)),
                ("occurred_at", models.DateTimeField(editable=False)),
                (
                    "runtime_error",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="occurrences",
                        to="operations.runtimeerror",
                    ),
                ),
            ],
            options={
                "db_table": "operations_runtime_error_occurrence",
                "ordering": ("-occurred_at", "-id"),
                "indexes": [
                    models.Index(
                        fields=["runtime_error", "occurred_at"],
                        name="runtime_occurrence_error_idx",
                    ),
                    models.Index(
                        fields=["occurred_at"], name="runtime_occurrence_seen_idx"
                    ),
                    models.Index(
                        fields=["trace_code"], name="runtime_occurrence_trace_idx"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("runtime_error", "trace_code"),
                        name="runtime_occurrence_error_trace_unique",
                    )
                ],
            },
        ),
    ]
