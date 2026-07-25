from apps.operations.queries.audit import audit_detail, search_audit
from apps.operations.queries.errors import error_detail, search_runtime_errors
from apps.operations.services.audit import (
    AuditRejected,
    AuditSchema,
    record_audit_entry,
    register_audit_schema,
)
from apps.operations.services.capacity import (
    CapacityOperation,
    filesystem_capacity_gate,
)
from apps.operations.services.celery import execute_celery_entry
from apps.operations.services.errors import capture_runtime_error
from apps.operations.services.tasks import RetryableTaskError, StartOutcome


def require_image_creation_capacity(path):
    return filesystem_capacity_gate(path).require(CapacityOperation.IMAGE_CREATE)


def require_text_creation_capacity(path):
    return filesystem_capacity_gate(path).require(CapacityOperation.TEXT_CREATE)


__all__ = [
    "AuditRejected",
    "AuditSchema",
    "RetryableTaskError",
    "StartOutcome",
    "capture_runtime_error",
    "require_image_creation_capacity",
    "require_text_creation_capacity",
    "audit_detail",
    "error_detail",
    "execute_celery_entry",
    "record_audit_entry",
    "register_audit_schema",
    "search_audit",
    "search_runtime_errors",
]
