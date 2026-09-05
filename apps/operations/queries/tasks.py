from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from django.core.paginator import Paginator

from apps.core.pagination import PageSlice
from apps.operations.models import TaskRun, TaskRunStatus

TASK_RUN_STATUSES = tuple(TaskRunStatus.values)

TaskRunMetadataProvider = Callable[[tuple[str, ...]], Mapping[str, "TaskRunMetadata"]]


@dataclass(frozen=True, slots=True)
class TaskRunMetadata:
    token_requested: int | None = None
    token_settled: int | None = None
    token_status: str | None = None
    invocation_total_tokens: int | None = None


def _metadata_for(
    metadata: Mapping[str, TaskRunMetadata], run_id: str
) -> TaskRunMetadata:
    value = metadata.get(run_id)
    if value is None:
        return TaskRunMetadata()
    if not isinstance(value, TaskRunMetadata):
        raise TypeError("metadata_provider returned an invalid task-run value")
    return value


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
    duration_seconds: int | None
    token_requested: int | None
    token_settled: int | None
    token_status: str | None
    invocation_total_tokens: int | None


def task_run_records(
    *,
    status: str = "",
    is_admin: bool,
    limit: int = 200,
    page: int | None = None,
    page_size: int = 20,
    metadata_provider: TaskRunMetadataProvider | None = None,
) -> tuple[TaskRunItem, ...] | PageSlice[TaskRunItem]:
    if not is_admin:
        raise PermissionError("Task-run access denied")
    if status and status not in TASK_RUN_STATUSES:
        raise ValueError("Invalid task-run status")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Invalid task-run limit")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Invalid task-run page")
    rows = TaskRun.objects.all()
    if status:
        rows = rows.filter(status=status)
    ordered = rows.order_by("-scheduled_at", "run_id")
    if page is None:
        task_rows = tuple(ordered[:limit])
        total_items = total_pages = None
        selected_page = 1
        selected_size = len(task_rows) or page_size
        has_previous = has_next = False
    else:
        paginator = Paginator(ordered, page_size)
        selected = paginator.get_page(page)
        task_rows = tuple(selected.object_list)
        total_items = paginator.count
        total_pages = paginator.num_pages
        selected_page = selected.number
        selected_size = page_size
        has_previous = selected.has_previous()
        has_next = selected.has_next()
    run_ids = tuple(row.run_id for row in task_rows)
    if metadata_provider is not None and not callable(metadata_provider):
        raise TypeError("metadata_provider must be callable")
    metadata = (
        metadata_provider(tuple(run_ids)) if metadata_provider is not None else {}
    )
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata_provider must return a mapping")
    items = tuple(
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
            duration_seconds=(
                max(0, int((row.completed_at - row.started_at).total_seconds()))
                if row.started_at is not None and row.completed_at is not None
                else None
            ),
            token_requested=(
                agent_metadata := _metadata_for(metadata, row.run_id)
            ).token_requested,
            token_settled=agent_metadata.token_settled,
            token_status=agent_metadata.token_status,
            invocation_total_tokens=agent_metadata.invocation_total_tokens,
        )
        for row in task_rows
    )
    if page is None:
        return items
    return PageSlice(
        items=items,
        page_number=selected_page,
        page_size=selected_size,
        total_items=total_items,
        total_pages=total_pages,
        has_previous=has_previous,
        has_next=has_next,
    )


__all__ = [
    "TASK_RUN_STATUSES",
    "TaskRunItem",
    "TaskRunMetadata",
    "TaskRunMetadataProvider",
    "task_run_records",
]
