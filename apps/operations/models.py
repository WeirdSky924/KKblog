from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.ids import new_ulid


class AuditEntry(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    trace_code = models.CharField(max_length=30, editable=False)
    actor_id = models.UUIDField(editable=False)
    action = models.CharField(max_length=96, editable=False)
    target_type = models.CharField(max_length=64, editable=False)
    target_id = models.CharField(max_length=128, editable=False)
    client_ip = models.GenericIPAddressField(
        protocol="both", unpack_ipv4=True, editable=False
    )
    summary = models.CharField(max_length=255, blank=True, editable=False)
    before_safe = models.JSONField(default=dict, editable=False)
    after_safe = models.JSONField(default=dict, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "operations_audit_entry"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("created_at",), name="audit_created_idx"),
            models.Index(fields=("action", "created_at"), name="audit_action_idx"),
            models.Index(fields=("target_type", "target_id"), name="audit_target_idx"),
        ]


class RuntimeError(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    error_code = models.CharField(max_length=96, editable=False)
    exception_type = models.CharField(max_length=192, editable=False)
    safe_summary = models.CharField(max_length=255, editable=False)
    safe_traceback = models.TextField(editable=False)
    safe_context = models.JSONField(default=dict, editable=False)
    latest_trace_code = models.CharField(max_length=30, editable=False)
    occurrence_count = models.PositiveIntegerField(default=1, editable=False)
    first_seen_at = models.DateTimeField(editable=False)
    last_seen_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "operations_runtime_error"
        ordering = ("-last_seen_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(occurrence_count__gte=1),
                name="operations_runtime_error_count_positive",
            )
        ]
        indexes = [
            models.Index(
                fields=("error_code", "last_seen_at"),
                name="runtime_error_code_idx",
            ),
            models.Index(fields=("last_seen_at",), name="runtime_error_seen_idx"),
        ]


class RuntimeErrorOccurrence(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    runtime_error = models.ForeignKey(
        RuntimeError,
        on_delete=models.PROTECT,
        related_name="occurrences",
        editable=False,
    )
    trace_code = models.CharField(max_length=30, editable=False)
    safe_context = models.JSONField(default=dict, editable=False)
    occurred_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "operations_runtime_error_occurrence"
        ordering = ("-occurred_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("runtime_error", "trace_code"),
                name="runtime_occurrence_error_trace_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("runtime_error", "occurred_at"),
                name="runtime_occurrence_error_idx",
            ),
            models.Index(fields=("occurred_at",), name="runtime_occurrence_seen_idx"),
            models.Index(fields=("trace_code",), name="runtime_occurrence_trace_idx"),
        ]


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
