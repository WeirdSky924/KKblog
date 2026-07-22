from django.db import models
from django.db.models import Q
from django.utils import timezone


class TaskRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    RETRY_WAIT = "retry_wait", "Retry wait"
    SUCCEEDED = "succeeded", "Succeeded"
    FINAL_FAILED = "final_failed", "Final failed"


class TaskRun(models.Model):
    run_id = models.CharField(primary_key=True, max_length=26, editable=False)
    task_name = models.CharField(max_length=128, editable=False)
    business_object = models.CharField(max_length=128, editable=False)
    idempotency_key = models.CharField(max_length=255, editable=False)
    celery_id = models.CharField(max_length=64, editable=False)
    trace_code = models.CharField(max_length=30, editable=False)
    status = models.CharField(
        max_length=16,
        choices=TaskRunStatus,
        default=TaskRunStatus.PENDING,
        editable=False,
    )
    attempt = models.PositiveSmallIntegerField(default=0, editable=False)
    scheduled_at = models.DateTimeField(editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False)
    started_at = models.DateTimeField(null=True, editable=False)
    completed_at = models.DateTimeField(null=True, editable=False)
    heartbeat_at = models.DateTimeField(null=True, editable=False)
    lease_token = models.UUIDField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    result_ref = models.CharField(max_length=255, blank=True, editable=False)
    last_error_code = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "operations_task_run"
        ordering = ("-scheduled_at", "run_id")
        constraints = [
            models.UniqueConstraint(
                fields=("task_name", "idempotency_key"),
                name="operations_task_idempotency_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=TaskRunStatus.PENDING, attempt=0)
                    | Q(
                        status__in=(
                            TaskRunStatus.RUNNING,
                            TaskRunStatus.RETRY_WAIT,
                            TaskRunStatus.SUCCEEDED,
                            TaskRunStatus.FINAL_FAILED,
                        ),
                        attempt__gte=1,
                    )
                ),
                name="operations_task_attempt_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=TaskRunStatus.RUNNING,
                        lease_token__isnull=False,
                        lease_expires_at__isnull=False,
                    )
                    | Q(
                        status__in=(
                            TaskRunStatus.PENDING,
                            TaskRunStatus.RETRY_WAIT,
                            TaskRunStatus.SUCCEEDED,
                            TaskRunStatus.FINAL_FAILED,
                        ),
                        lease_token__isnull=True,
                        lease_expires_at__isnull=True,
                    )
                ),
                name="operations_task_lease_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=(
                            TaskRunStatus.PENDING,
                            TaskRunStatus.RUNNING,
                            TaskRunStatus.RETRY_WAIT,
                        ),
                        completed_at__isnull=True,
                    )
                    | Q(
                        status__in=(
                            TaskRunStatus.SUCCEEDED,
                            TaskRunStatus.FINAL_FAILED,
                        ),
                        completed_at__isnull=False,
                    )
                ),
                name="operations_task_completion_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "available_at"),
                name="operations_task_ready_idx",
                condition=Q(
                    status__in=(TaskRunStatus.PENDING, TaskRunStatus.RETRY_WAIT)
                ),
            ),
            models.Index(
                fields=("lease_expires_at",),
                name="operations_task_lease_idx",
                condition=Q(status=TaskRunStatus.RUNNING),
            ),
        ]
