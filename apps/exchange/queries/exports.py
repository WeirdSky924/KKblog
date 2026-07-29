from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from apps.core.ids import normalize_ulid

from ..models import ExportJob


@dataclass(frozen=True, slots=True)
class ExportJobItem:
    job_id: str
    scope: str
    scope_author_id: UUID | None
    scope_section_id: UUID | None
    requested_article_ids: tuple[str, ...]
    selected_count: int
    other_author_count: int
    state: str
    archive_size_bytes: int | None
    error_code: str
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None
    cancel_requested_at: datetime | None
    expires_at: datetime | None
    expired_at: datetime | None
    can_cancel: bool
    can_download: bool


def _actor(value, *, is_admin: bool) -> UUID:
    if not is_admin:
        raise PermissionError("Export job access denied")
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise PermissionError("Export job access denied") from None


def _item(job: ExportJob, *, now: datetime) -> ExportJobItem:
    summary = job.selection_summary
    return ExportJobItem(
        job_id=job.id,
        scope=job.scope,
        scope_author_id=job.scope_author_id,
        scope_section_id=job.scope_section_id,
        requested_article_ids=tuple(job.requested_article_ids),
        selected_count=int(summary.get("selected_count", 0)),
        other_author_count=int(summary.get("other_author_count", 0)),
        state=job.state,
        archive_size_bytes=job.archive_size_bytes,
        error_code=job.error_code,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        cancel_requested_at=job.cancel_requested_at,
        expires_at=job.expires_at,
        expired_at=job.expired_at,
        can_cancel=job.state == ExportJob.State.RUNNING,
        can_download=(
            job.state == ExportJob.State.COMPLETED
            and job.expires_at is not None
            and job.expires_at > now
        ),
    )


def export_job_records(
    *, actor_id, is_admin: bool, limit: int = 100
) -> tuple[ExportJobItem, ...]:
    actor = _actor(actor_id, is_admin=is_admin)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Invalid export job limit")
    now = timezone.now()
    return tuple(
        _item(job, now=now)
        for job in ExportJob.objects.filter(requested_by_id=actor).order_by(
            "-created_at", "-id"
        )[:limit]
    )


def export_job_detail(*, actor_id, job_id: str, is_admin: bool) -> ExportJobItem:
    actor = _actor(actor_id, is_admin=is_admin)
    try:
        identity = normalize_ulid(job_id)
    except (TypeError, ValueError):
        raise LookupError("Export job not found") from None
    job = ExportJob.objects.filter(pk=identity, requested_by_id=actor).first()
    if job is None:
        raise LookupError("Export job not found")
    return _item(job, now=timezone.now())


__all__ = ["ExportJobItem", "export_job_detail", "export_job_records"]
