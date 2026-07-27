from pathlib import Path

from django.conf import settings

from apps.operations.public import (
    BackupStorage,
    PostgresDumpConfig,
    PostgresDumpRunner,
    build_weekly_backup,
    due_backup_expiry_ids,
    expire_backup,
    mark_backup_task_final_failed,
)


def configured_backup_storage() -> BackupStorage:
    return BackupStorage(settings.BACKUP_ROOT)


def configured_postgres_dump_runner() -> PostgresDumpRunner:
    database = settings.DATABASES["default"]
    if not str(database.get("ENGINE", "")).endswith("postgresql"):
        raise RuntimeError("PostgreSQL backup requires the PostgreSQL backend")
    try:
        port = int(database.get("PORT") or 5432)
    except (TypeError, ValueError):
        raise RuntimeError("PostgreSQL backup configuration is invalid") from None
    return PostgresDumpRunner(
        PostgresDumpConfig(
            executable=Path(settings.BACKUP_PG_DUMP_BINARY),
            database=str(database.get("NAME", "")),
            username=str(database.get("USER", "")),
            password=str(database.get("PASSWORD", "")),
            host=str(database.get("HOST", "")),
            port=port,
        ),
        poll_seconds=settings.BACKUP_HEARTBEAT_INTERVAL_SECONDS,
    )


def build_configured_weekly_backup(week_id: str, *, heartbeat=lambda: None):
    return build_weekly_backup(
        week_id=week_id,
        destination=settings.BACKUP_DESTINATION,
        storage=configured_backup_storage(),
        media_root=settings.MEDIA_ROOT,
        database_dumper=configured_postgres_dump_runner(),
        heartbeat=heartbeat,
    )


def configured_due_backup_expiry_ids() -> tuple[str, ...]:
    return due_backup_expiry_ids(batch_size=settings.BACKUP_EXPIRY_BATCH_SIZE)


def expire_configured_backup(backup_id: str):
    return expire_backup(
        backup_id=backup_id,
        storage=configured_backup_storage(),
    )


def mark_configured_backup_final_failed(*, week_id: str, error_code: str):
    return mark_backup_task_final_failed(
        week_id=week_id,
        error_code=error_code,
        storage=configured_backup_storage(),
    )
