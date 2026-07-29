from dataclasses import dataclass
from datetime import datetime

from apps.operations.models import TaskRun, TaskRunStatus

TASK_RUN_STATUSES = tuple(TaskRunStatus.values)


@dataclass(frozen=True, slots=True)
class TaskRunItem:
    run_id: str
    task_name: str
    business_object: str
    trace_code: str
    status: str
    attempt: int
    scheduled_at: datetime
    available_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    last_error_code: str


def task_run_records(
    *,
    status: str = "",
    is_admin: bool,
    limit: int = 200,
) -> tuple[TaskRunItem, ...]:
    if not is_admin:
        raise PermissionError("Task-run access denied")
    if status and status not in TASK_RUN_STATUSES:
        raise ValueError("Invalid task-run status")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Invalid task-run limit")
    rows = TaskRun.objects.all()
    if status:
        rows = rows.filter(status=status)
    return tuple(
        TaskRunItem(
            run_id=row.run_id,
            task_name=row.task_name,
            business_object=row.business_object,
            trace_code=row.trace_code,
            status=row.status,
            attempt=row.attempt,
            scheduled_at=row.scheduled_at,
            available_at=row.available_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            heartbeat_at=row.heartbeat_at,
            lease_expires_at=row.lease_expires_at,
            last_error_code=row.last_error_code,
        )
        for row in rows.order_by("-scheduled_at", "run_id")[:limit]
    )


__all__ = ["TASK_RUN_STATUSES", "TaskRunItem", "task_run_records"]
