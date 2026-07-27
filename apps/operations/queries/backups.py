from dataclasses import dataclass
from datetime import datetime

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


def backup_records(*, limit: int = 100) -> tuple[BackupRecordItem, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Backup record limit is invalid")
    return tuple(
        BackupRecordItem(
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
        for record in BackupRecord.objects.order_by("-started_at", "-id")[:limit]
    )
