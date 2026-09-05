from dataclasses import dataclass
from datetime import datetime

from django.core.paginator import Paginator

from apps.core.pagination import PageSlice
from apps.operations.models import BackupRecord


@dataclass(frozen=True, slots=True)
class BackupRecordItem:
    backup_id: str
    week_id: str
    destination: str
    state: str
    started_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    archive_size_bytes: int | None
    database_size_bytes: int | None
    media_size_bytes: int | None
    media_file_count: int | None
    error_code: str
    encrypted: bool = False
    automatic_integrity_verified: bool = False
    restore_verified: bool = False


def backup_records(
    *,
    is_admin: bool,
    limit: int = 100,
    page: int | None = None,
    page_size: int = 20,
) -> tuple[BackupRecordItem, ...] | PageSlice[BackupRecordItem]:
    if not is_admin:
        raise PermissionError("Backup record access denied")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Backup record limit is invalid")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise ValueError("Backup record page is invalid")

    def item(record: BackupRecord) -> BackupRecordItem:
        return BackupRecordItem(
            backup_id=record.id,
            week_id=record.week_id,
            destination=record.destination,
            state=record.state,
            started_at=record.started_at,
            completed_at=record.completed_at,
            expires_at=record.expires_at,
            archive_size_bytes=record.archive_size_bytes,
            database_size_bytes=record.database_size_bytes,
            media_size_bytes=record.media_size_bytes,
            media_file_count=record.media_file_count,
            error_code=record.error_code,
        )

    ordered = BackupRecord.objects.order_by("-started_at", "-id")
    if page is None:
        return tuple(item(record) for record in ordered[:limit])
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(item(record) for record in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )
