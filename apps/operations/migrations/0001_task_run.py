import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TaskRun",
            fields=[
                (
                    "run_id",
                    models.CharField(
                        editable=False,
                        max_length=26,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("task_name", models.CharField(editable=False, max_length=128)),
                (
                    "business_object",
                    models.CharField(editable=False, max_length=128),
                ),
                (
                    "idempotency_key",
                    models.CharField(editable=False, max_length=255),
                ),
                ("celery_id", models.CharField(editable=False, max_length=64)),
                ("trace_code", models.CharField(editable=False, max_length=30)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("retry_wait", "Retry wait"),
                            ("succeeded", "Succeeded"),
                            ("final_failed", "Final failed"),
                        ],
                        default="pending",
                        editable=False,
                        max_length=16,
                    ),
                ),
                (
                    "attempt",
                    models.PositiveSmallIntegerField(default=0, editable=False),
                ),
                ("scheduled_at", models.DateTimeField(editable=False)),
                (
                    "available_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, editable=False
                    ),
                ),
                ("started_at", models.DateTimeField(editable=False, null=True)),
                ("completed_at", models.DateTimeField(editable=False, null=True)),
                ("heartbeat_at", models.DateTimeField(editable=False, null=True)),
                ("lease_token", models.UUIDField(editable=False, null=True)),
                (
                    "lease_expires_at",
                    models.DateTimeField(editable=False, null=True),
                ),
                (
                    "result_ref",
                    models.CharField(blank=True, editable=False, max_length=255),
                ),
                (
                    "last_error_code",
                    models.CharField(blank=True, editable=False, max_length=64),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, editable=False),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, editable=False),
                ),
            ],
            options={
                "db_table": "operations_task_run",
                "ordering": ("-scheduled_at", "run_id"),
                "indexes": [
                    models.Index(
                        condition=models.Q(("status__in", ("pending", "retry_wait"))),
                        fields=["status", "available_at"],
                        name="operations_task_ready_idx",
                    ),
                    models.Index(
                        condition=models.Q(("status", "running")),
                        fields=["lease_expires_at"],
                        name="operations_task_lease_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("task_name", "idempotency_key"),
                        name="operations_task_idempotency_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("attempt", 0), ("status", "pending")),
                            models.Q(
                                ("attempt__gte", 1),
                                (
                                    "status__in",
                                    (
                                        "running",
                                        "retry_wait",
                                        "succeeded",
                                        "final_failed",
                                    ),
                                ),
                            ),
                            _connector="OR",
                        ),
                        name="operations_task_attempt_shape",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("lease_expires_at__isnull", False),
                                ("lease_token__isnull", False),
                                ("status", "running"),
                            ),
                            models.Q(
                                ("lease_expires_at__isnull", True),
                                ("lease_token__isnull", True),
                                (
                                    "status__in",
                                    (
                                        "pending",
                                        "retry_wait",
                                        "succeeded",
                                        "final_failed",
                                    ),
                                ),
                            ),
                            _connector="OR",
                        ),
                        name="operations_task_lease_shape",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("completed_at__isnull", True),
                                (
                                    "status__in",
                                    ("pending", "running", "retry_wait"),
                                ),
                            ),
                            models.Q(
                                ("completed_at__isnull", False),
                                (
                                    "status__in",
                                    ("succeeded", "final_failed"),
                                ),
                            ),
                            _connector="OR",
                        ),
                        name="operations_task_completion_shape",
                    ),
                ],
            },
        ),
    ]
