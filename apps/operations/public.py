from apps.operations.queries.audit import audit_detail, search_audit
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
from apps.operations.services.tasks import RetryableTaskError, StartOutcome


def require_image_creation_capacity(path):
    return filesystem_capacity_gate(path).require(CapacityOperation.IMAGE_CREATE)


__all__ = [
    "AuditRejected",
    "AuditSchema",
    "RetryableTaskError",
    "StartOutcome",
    "require_image_creation_capacity",
    "audit_detail",
    "execute_celery_entry",
    "record_audit_entry",
    "register_audit_schema",
    "search_audit",
]
