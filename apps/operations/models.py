from django.db import models
from django.db.models import F, Q
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


class CapacitySnapshotState(models.TextChoices):
    NORMAL = "normal", "Normal"
    WARN = "warn", "Warning"
    NO_IMAGE = "no_image", "No image creation"
    READ_ONLY = "read_only", "Read only"


class CapacitySnapshot(models.Model):
    source_key = models.CharField(primary_key=True, max_length=64, editable=False)
    state = models.CharField(
        max_length=12,
        choices=CapacitySnapshotState,
        editable=False,
    )
    total_bytes = models.BigIntegerField(editable=False)
    free_bytes = models.BigIntegerField(editable=False)
    observed_at = models.DateTimeField(editable=False)
    state_changed_at = models.DateTimeField(editable=False)
    sample_count = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "operations_capacity_snapshot"
        ordering = ("source_key",)
        constraints = [
            models.CheckConstraint(
                condition=Q(state__in=CapacitySnapshotState.values),
                name="ops_capacity_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(total_bytes__gt=0),
                name="operations_capacity_total_positive",
            ),
            models.CheckConstraint(
                condition=Q(free_bytes__gte=0) & Q(free_bytes__lte=F("total_bytes")),
                name="operations_capacity_free_range",
            ),
            models.CheckConstraint(
                condition=Q(sample_count__gte=1),
                name="operations_capacity_samples_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "observed_at"),
                name="operations_capacity_state_idx",
            )
        ]


class ServiceHealthStatus(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    UNAVAILABLE = "unavailable", "Unavailable"


class ServiceHealthSnapshot(models.Model):
    source_key = models.CharField(primary_key=True, max_length=64, editable=False)
    status = models.CharField(
        max_length=12,
        choices=ServiceHealthStatus,
        editable=False,
    )
    check_count = models.PositiveBigIntegerField(default=1, editable=False)
    consecutive_failures = models.PositiveIntegerField(default=0, editable=False)
    first_checked_at = models.DateTimeField(editable=False)
    last_checked_at = models.DateTimeField(editable=False)
    status_changed_at = models.DateTimeField(editable=False)
    last_success_at = models.DateTimeField(null=True, editable=False)
    last_error_code = models.CharField(max_length=96, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "operations_service_health_snapshot"
        ordering = ("source_key",)
        constraints = [
            models.CheckConstraint(
                condition=Q(check_count__gte=1),
                name="operations_health_checks_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=ServiceHealthStatus.HEALTHY,
                        consecutive_failures=0,
                        last_error_code="",
                        last_success_at__isnull=False,
                    )
                    | (
                        Q(
                            status=ServiceHealthStatus.UNAVAILABLE,
                            consecutive_failures__gte=1,
                        )
                        & ~Q(last_error_code="")
                    )
                ),
                name="operations_health_state_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "last_checked_at"),
                name="operations_health_status_idx",
            )
        ]


class OperationalAlertKind(models.TextChoices):
    TASK_FINAL_FAILED = "task_final_failed", "Task final failed"
    CAPACITY = "capacity", "Capacity"
    SERVICE_HEALTH = "service_health", "Service health"


class OperationalAlertSeverity(models.TextChoices):
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class OperationalAlert(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    kind = models.CharField(max_length=24, choices=OperationalAlertKind, editable=False)
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    source_key = models.CharField(max_length=128, editable=False)
    task_run = models.ForeignKey(
        "operations.TaskRun",
        related_name="operational_alerts",
        null=True,
        on_delete=models.PROTECT,
        editable=False,
    )
    runtime_error = models.ForeignKey(
        RuntimeError,
        related_name="operational_alerts",
        null=True,
        on_delete=models.PROTECT,
        editable=False,
    )
    task_name = models.CharField(max_length=128, blank=True, editable=False)
    error_code = models.CharField(max_length=96, editable=False)
    trace_code = models.CharField(max_length=30, editable=False)
    state_code = models.CharField(max_length=32, blank=True, editable=False)
    severity = models.CharField(
        max_length=12,
        choices=OperationalAlertSeverity,
        default=OperationalAlertSeverity.CRITICAL,
        editable=False,
    )
    active = models.BooleanField(default=True, editable=False)
    occurrence_count = models.PositiveIntegerField(default=1, editable=False)
    first_seen_at = models.DateTimeField(editable=False)
    last_seen_at = models.DateTimeField(editable=False)
    resolved_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        db_table = "operations_operational_alert"
        ordering = ("-last_seen_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(occurrence_count__gte=1),
                name="operations_alert_count_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(active=True, resolved_at__isnull=True)
                    | Q(active=False, resolved_at__isnull=False)
                ),
                name="operations_alert_resolution_shape",
            ),
            models.UniqueConstraint(
                fields=("kind", "source_key"),
                condition=Q(active=True),
                name="operations_alert_active_source_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind=OperationalAlertKind.TASK_FINAL_FAILED, state_code="")
                    | Q(
                        kind=OperationalAlertKind.CAPACITY,
                        state_code__in=CapacitySnapshotState.values,
                    )
                    | Q(
                        kind=OperationalAlertKind.SERVICE_HEALTH,
                        state_code__in=ServiceHealthStatus.values,
                    )
                ),
                name="ops_alert_state_code_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("active", "kind", "last_seen_at"),
                name="operations_alert_active_idx",
            ),
            models.Index(fields=("source_key",), name="operations_alert_source_idx"),
        ]


class AlertEmailStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    UNKNOWN = "unknown", "Delivery unknown"


class OperationalAlertEmailWindow(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    alert = models.ForeignKey(
        OperationalAlert,
        related_name="email_windows",
        on_delete=models.PROTECT,
        editable=False,
    )
    window_started_at = models.DateTimeField(editable=False)
    status = models.CharField(
        max_length=12,
        choices=AlertEmailStatus,
        default=AlertEmailStatus.PENDING,
        editable=False,
    )
    attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False)
    lease_token = models.UUIDField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    sent_at = models.DateTimeField(null=True, editable=False)
    last_error_code = models.CharField(max_length=96, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "operations_alert_email_window"
        ordering = ("window_started_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("alert", "window_started_at"),
                name="operations_alert_email_window_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=AlertEmailStatus.SENDING,
                        attempts__gte=1,
                        lease_token__isnull=False,
                        lease_expires_at__isnull=False,
                        sent_at__isnull=True,
                    )
                    | Q(
                        status=AlertEmailStatus.SENT,
                        attempts__gte=1,
                        lease_token__isnull=True,
                        lease_expires_at__isnull=True,
                        sent_at__isnull=False,
                    )
                    | Q(
                        status__in=(
                            AlertEmailStatus.FAILED,
                            AlertEmailStatus.UNKNOWN,
                        ),
                        attempts__gte=1,
                        lease_token__isnull=True,
                        lease_expires_at__isnull=True,
                        sent_at__isnull=True,
                    )
                    | Q(
                        status=AlertEmailStatus.PENDING,
                        attempts=0,
                        lease_token__isnull=True,
                        lease_expires_at__isnull=True,
                        sent_at__isnull=True,
                    )
                ),
                name="operations_alert_email_state_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "available_at"),
                name="ops_alert_email_ready_idx",
                condition=Q(
                    status__in=(AlertEmailStatus.PENDING, AlertEmailStatus.FAILED)
                ),
            ),
            models.Index(
                fields=("lease_expires_at",),
                name="ops_alert_email_lease_idx",
                condition=Q(status=AlertEmailStatus.SENDING),
            ),
        ]


class BackupRecord(models.Model):
    class State(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"

    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    week_id = models.CharField(max_length=8, editable=False)
    destination = models.CharField(max_length=8, default="local", editable=False)
    state = models.CharField(
        max_length=12,
        choices=State.choices,
        default=State.RUNNING,
        editable=False,
    )
    archive_key = models.CharField(max_length=512, blank=True, editable=False)
    archive_size_bytes = models.PositiveBigIntegerField(null=True, editable=False)
    archive_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    database_size_bytes = models.PositiveBigIntegerField(null=True, editable=False)
    media_size_bytes = models.PositiveBigIntegerField(null=True, editable=False)
    media_file_count = models.PositiveIntegerField(null=True, editable=False)
    error_code = models.CharField(max_length=96, blank=True, editable=False)
    started_at = models.DateTimeField(editable=False)
    heartbeat_at = models.DateTimeField(editable=False)
    lease_token = models.UUIDField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    completed_at = models.DateTimeField(null=True, editable=False)
    expires_at = models.DateTimeField(null=True, editable=False)
    expired_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "operations_backup_record"
        ordering = ("-started_at", "-id")
        indexes = [
            models.Index(
                fields=("state", "started_at"),
                name="operations_backup_state_idx",
            ),
            models.Index(
                fields=("expires_at", "id"),
                condition=Q(state="COMPLETED"),
                name="operations_backup_expiry_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("destination", "week_id"),
                name="operations_backup_week_unique",
            ),
            models.UniqueConstraint(
                models.Value(1),
                condition=Q(state="RUNNING"),
                name="operations_backup_running_unique",
            ),
            models.CheckConstraint(
                condition=Q(destination="local"),
                name="operations_backup_destination_local",
            ),
            models.CheckConstraint(
                condition=Q(week_id__regex=r"^[0-9]{4}-W[0-9]{2}$"),
                name="operations_backup_week_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state="RUNNING",
                        archive_key="",
                        archive_size_bytes__isnull=True,
                        archive_sha256="",
                        database_size_bytes__isnull=True,
                        media_size_bytes__isnull=True,
                        media_file_count__isnull=True,
                        error_code="",
                        lease_token__isnull=False,
                        lease_expires_at__isnull=False,
                        completed_at__isnull=True,
                        expires_at__isnull=True,
                        expired_at__isnull=True,
                    )
                    | (
                        Q(
                            state="COMPLETED",
                            archive_size_bytes__isnull=False,
                            database_size_bytes__isnull=False,
                            media_size_bytes__isnull=False,
                            media_file_count__isnull=False,
                            error_code="",
                            lease_token__isnull=True,
                            lease_expires_at__isnull=True,
                            completed_at__isnull=False,
                            expires_at__isnull=False,
                            expired_at__isnull=True,
                        )
                        & ~Q(archive_key="")
                        & Q(archive_sha256__regex=r"^[0-9a-f]{64}$")
                    )
                    | (
                        Q(
                            state="FAILED",
                            archive_key="",
                            archive_size_bytes__isnull=True,
                            archive_sha256="",
                            database_size_bytes__isnull=True,
                            media_size_bytes__isnull=True,
                            media_file_count__isnull=True,
                            lease_token__isnull=True,
                            lease_expires_at__isnull=True,
                            completed_at__isnull=False,
                            expires_at__isnull=True,
                            expired_at__isnull=True,
                        )
                        & ~Q(error_code="")
                    )
                    | (
                        Q(
                            state="EXPIRED",
                            archive_key="",
                            archive_size_bytes__isnull=False,
                            database_size_bytes__isnull=False,
                            media_size_bytes__isnull=False,
                            media_file_count__isnull=False,
                            error_code="",
                            lease_token__isnull=True,
                            lease_expires_at__isnull=True,
                            completed_at__isnull=False,
                            expires_at__isnull=False,
                            expired_at__isnull=False,
                        )
                        & Q(archive_sha256__regex=r"^[0-9a-f]{64}$")
                    )
                ),
                name="operations_backup_state_shape",
            ),
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
