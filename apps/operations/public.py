from apps.operations.backup_storage import BackupStorage
from apps.operations.consumers import (
    consume_backup_task_final_failure,
    consume_task_final_failure_alert,
)
from apps.operations.postgres_backup import PostgresDumpConfig, PostgresDumpRunner
from apps.operations.queries.audit import audit_detail, search_audit
from apps.operations.queries.backups import backup_records
from apps.operations.queries.errors import error_detail, search_runtime_errors
from apps.operations.queries.monitoring import current_monitoring_status
from apps.operations.queries.tasks import TASK_RUN_STATUSES, task_run_records
from apps.operations.services.alerts import (
    is_operational_task,
    send_pending_operational_alert_emails,
)
from apps.operations.services.audit import (
    AuditRejected,
    AuditSchema,
    record_audit_entry,
    register_audit_schema,
)
from apps.operations.services.backup import (
    BackupRetryable,
    build_weekly_backup,
    due_backup_expiry_ids,
    expire_backup,
    mark_backup_task_final_failed,
    shanghai_backup_week,
)
from apps.operations.services.capacity import (
    CapacityOperation,
    filesystem_capacity_gate,
)
from apps.operations.services.celery import execute_celery_entry
from apps.operations.services.errors import capture_runtime_error
from apps.operations.services.tasks import (
    RetryableTaskError,
    StartOutcome,
    TaskFinalFailed,
    TaskRetryScheduled,
    execute_tracked_task,
)


def require_image_creation_capacity(path):
    return filesystem_capacity_gate(path).require(CapacityOperation.IMAGE_CREATE)


def require_text_creation_capacity(path):
    return filesystem_capacity_gate(path).require(CapacityOperation.TEXT_CREATE)


__all__ = [
    "AuditRejected",
    "AuditSchema",
    "BackupRetryable",
    "BackupStorage",
    "PostgresDumpConfig",
    "PostgresDumpRunner",
    "RetryableTaskError",
    "StartOutcome",
    "TaskFinalFailed",
    "TaskRetryScheduled",
    "TASK_RUN_STATUSES",
    "capture_runtime_error",
    "consume_backup_task_final_failure",
    "consume_task_final_failure_alert",
    "current_monitoring_status",
    "require_image_creation_capacity",
    "require_text_creation_capacity",
    "audit_detail",
    "backup_records",
    "build_weekly_backup",
    "due_backup_expiry_ids",
    "error_detail",
    "execute_celery_entry",
    "execute_tracked_task",
    "expire_backup",
    "mark_backup_task_final_failed",
    "record_audit_entry",
    "register_audit_schema",
    "search_audit",
    "search_runtime_errors",
    "send_pending_operational_alert_emails",
    "is_operational_task",
    "shanghai_backup_week",
    "task_run_records",
]
