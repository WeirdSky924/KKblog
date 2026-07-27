import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from django.db import IntegrityError, transaction

from apps.core.ids import new_uuid
from apps.core.time.clock import Clock, SystemClock
from apps.core.time.shanghai import shanghai_business_date
from apps.operations.backup_archive import write_backup_archive
from apps.operations.backup_storage import BackupStorage, BackupStorageBoundaryError
from apps.operations.models import BackupRecord

_WEEK_ID = re.compile(r"^(?P<year>[0-9]{4})-W(?P<week>[0-9]{2})$")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_LEASE_SECONDS = 1_800
_RETENTION = timedelta(days=30)

Heartbeat = Callable[[], object]
DatabaseDumper = Callable[[Path, Heartbeat], object]


class BackupError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class BackupRetryable(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = _safe_error_code(error_code)
        super().__init__(self.error_code)


@dataclass(frozen=True, slots=True)
class BackupBuildResult:
    backup_id: str
    week_id: str
    state: str
    archive_size_bytes: int | None
    archive_sha256: str
    database_size_bytes: int | None
    media_size_bytes: int | None
    media_file_count: int | None


@dataclass(frozen=True, slots=True)
class BackupExpireResult:
    backup_id: str
    state: str
    removed: bool


@dataclass(frozen=True, slots=True)
class BackupFailureResult:
    backup_id: str
    state: str


def _safe_error_code(value: str) -> str:
    if not isinstance(value, str) or _ERROR_CODE.fullmatch(value) is None:
        return "operations.backup_build_failed.v1"
    return value


def _week_id(value: str) -> str:
    if not isinstance(value, str):
        raise BackupError("operations.backup_week_invalid.v1", "备份周标识无效。")
    match = _WEEK_ID.fullmatch(value)
    if match is None:
        raise BackupError("operations.backup_week_invalid.v1", "备份周标识无效。")
    year = int(match.group("year"))
    week = int(match.group("week"))
    try:
        from datetime import date

        date.fromisocalendar(year, week, 1)
    except ValueError:
        raise BackupError(
            "operations.backup_week_invalid.v1", "备份周标识无效。"
        ) from None
    return value


def _destination(value: str) -> str:
    if value != "local":
        raise BackupError(
            "operations.backup_destination_invalid.v1", "首版备份目标只能是 local。"
        )
    return value


def shanghai_backup_week(*, clock: Clock | None = None) -> str:
    business_date = shanghai_business_date((clock or SystemClock()).now())
    iso = business_date.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def _result(record: BackupRecord) -> BackupBuildResult:
    return BackupBuildResult(
        record.id,
        record.week_id,
        record.state,
        record.archive_size_bytes,
        record.archive_sha256,
        record.database_size_bytes,
        record.media_size_bytes,
        record.media_file_count,
    )


def _prepare_record(
    *, week_id: str, destination: str, clock: Clock
) -> tuple[BackupRecord, object | None]:
    now = clock.now()
    with transaction.atomic():
        existing = (
            BackupRecord.objects.select_for_update()
            .filter(week_id=week_id, destination=destination)
            .first()
        )
        if existing is not None:
            if existing.state != BackupRecord.State.RUNNING:
                return existing, None
            if (
                existing.lease_token is not None
                and existing.lease_expires_at is not None
                and existing.lease_expires_at > now
            ):
                raise BackupRetryable("operations.backup_already_running.v1")
            lease_token = new_uuid()
            existing.heartbeat_at = now
            existing.lease_token = lease_token
            existing.lease_expires_at = now + timedelta(seconds=_LEASE_SECONDS)
            existing.save(
                update_fields=("heartbeat_at", "lease_token", "lease_expires_at")
            )
            return existing, lease_token
        if (
            BackupRecord.objects.select_for_update()
            .filter(state=BackupRecord.State.RUNNING)
            .exists()
        ):
            raise BackupRetryable("operations.backup_already_running.v1")
        lease_token = new_uuid()
        try:
            record = BackupRecord.objects.create(
                week_id=week_id,
                destination=destination,
                started_at=now,
                heartbeat_at=now,
                lease_token=lease_token,
                lease_expires_at=now + timedelta(seconds=_LEASE_SECONDS),
            )
        except IntegrityError:
            raise BackupRetryable("operations.backup_already_running.v1") from None
        return record, lease_token


def _progress(
    record_id: str, lease_token, *, heartbeat: Heartbeat, clock: Clock
) -> None:
    if not callable(heartbeat):
        raise TypeError("Backup heartbeat is required")
    heartbeat()
    now = clock.now()
    updated = BackupRecord.objects.filter(
        pk=record_id,
        state=BackupRecord.State.RUNNING,
        lease_token=lease_token,
        lease_expires_at__gt=now,
    ).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=_LEASE_SECONDS),
    )
    if updated != 1:
        raise BackupRetryable("operations.backup_state_changed.v1")


def _digest(stream) -> tuple[int, str]:
    digest = sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _cleanup_build(storage: BackupStorage, backup_id: str, lease_token) -> None:
    storage.discard_part(backup_id, lease_token)
    storage.cleanup_workspace(backup_id, lease_token)


def _release_attempt(record_id: str, lease_token, *, clock: Clock) -> None:
    now = clock.now()
    BackupRecord.objects.filter(
        pk=record_id,
        state=BackupRecord.State.RUNNING,
        lease_token=lease_token,
    ).update(heartbeat_at=now, lease_expires_at=now)


def _discard_committed_attempt(
    storage: BackupStorage, record_id: str, lease_token, archive_key: str
) -> None:
    with transaction.atomic():
        record = BackupRecord.objects.select_for_update().get(pk=record_id)
        if (
            record.state == BackupRecord.State.RUNNING
            and record.lease_token == lease_token
        ):
            storage.delete_archive(archive_key)


def build_weekly_backup(
    *,
    week_id: str,
    destination: str,
    storage: BackupStorage,
    media_root: Path | str,
    database_dumper: DatabaseDumper,
    heartbeat: Heartbeat = lambda: None,
    clock: Clock | None = None,
) -> BackupBuildResult:
    normalized_week = _week_id(week_id)
    normalized_destination = _destination(destination)
    if not isinstance(storage, BackupStorage) or not callable(database_dumper):
        raise TypeError("Backup ports are required")
    active_clock = clock or SystemClock()
    record, lease_token = _prepare_record(
        week_id=normalized_week,
        destination=normalized_destination,
        clock=active_clock,
    )
    if record.state != BackupRecord.State.RUNNING:
        return _result(record)
    if lease_token is None:
        raise BackupRetryable("operations.backup_state_changed.v1")
    archive_key = storage.archive_key(record.id)
    try:
        if storage.archive_exists(archive_key):
            storage.delete_archive(archive_key)
        storage.cleanup_attempts(record.id)
    except (BackupStorageBoundaryError, OSError):
        _release_attempt(record.id, lease_token, clock=active_clock)
        raise BackupRetryable("operations.backup_archive_conflict.v1") from None
    storage.prepare_workspace(record.id, lease_token)
    dump_path = storage.database_dump_path(record.id, lease_token)
    committed = False
    archive_key = ""
    try:
        _progress(record.id, lease_token, heartbeat=heartbeat, clock=active_clock)
        database_dumper(
            dump_path,
            lambda: _progress(
                record.id, lease_token, heartbeat=heartbeat, clock=active_clock
            ),
        )
        _progress(record.id, lease_token, heartbeat=heartbeat, clock=active_clock)
        with storage.open_part(record.id, lease_token) as stream:
            summary = write_backup_archive(
                stream,
                backup_id=record.id,
                week_id=normalized_week,
                generated_at=active_clock.now(),
                database_dump=dump_path,
                media_root=Path(media_root),
                backup_root=storage.root,
                heartbeat=lambda: _progress(
                    record.id,
                    lease_token,
                    heartbeat=heartbeat,
                    clock=active_clock,
                ),
            )
            stream.flush()
            os.fsync(stream.fileno())
        with storage.open_part_read(record.id, lease_token) as stream:
            archive_size, archive_sha = _digest(stream)
        with transaction.atomic():
            locked = BackupRecord.objects.select_for_update().get(pk=record.id)
            if (
                locked.state != BackupRecord.State.RUNNING
                or locked.lease_token != lease_token
            ):
                raise BackupRetryable("operations.backup_state_changed.v1")
            archive_key = storage.commit_part(record.id, lease_token)
            committed = True
            now = active_clock.now()
            locked.state = BackupRecord.State.COMPLETED
            locked.archive_key = archive_key
            locked.archive_size_bytes = archive_size
            locked.archive_sha256 = archive_sha
            locked.database_size_bytes = summary.database_size_bytes
            locked.media_size_bytes = summary.media_size_bytes
            locked.media_file_count = summary.media_file_count
            locked.completed_at = now
            locked.expires_at = now + _RETENTION
            locked.heartbeat_at = now
            locked.lease_token = None
            locked.lease_expires_at = None
            locked.save(
                update_fields=(
                    "state",
                    "archive_key",
                    "archive_size_bytes",
                    "archive_sha256",
                    "database_size_bytes",
                    "media_size_bytes",
                    "media_file_count",
                    "completed_at",
                    "expires_at",
                    "heartbeat_at",
                    "lease_token",
                    "lease_expires_at",
                )
            )
    except BackupRetryable:
        if committed and archive_key:
            _discard_committed_attempt(storage, record.id, lease_token, archive_key)
        _cleanup_build(storage, record.id, lease_token)
        _release_attempt(record.id, lease_token, clock=active_clock)
        raise
    except Exception as exc:
        if committed and archive_key:
            _discard_committed_attempt(storage, record.id, lease_token, archive_key)
        _cleanup_build(storage, record.id, lease_token)
        _release_attempt(record.id, lease_token, clock=active_clock)
        error_code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
        raise BackupRetryable(_safe_error_code(error_code)) from None
    finally:
        storage.cleanup_workspace(record.id, lease_token)
    return _result(BackupRecord.objects.get(pk=record.id))


def due_backup_expiry_ids(
    *,
    batch_size: int = 100,
    clock: Clock | None = None,
) -> tuple[str, ...]:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1000
    ):
        raise ValueError("Backup expiry batch size is invalid")
    now = (clock or SystemClock()).now()
    return tuple(
        BackupRecord.objects.filter(
            state=BackupRecord.State.COMPLETED,
            expires_at__lte=now,
        )
        .order_by("expires_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )


def expire_backup(
    *,
    backup_id: str,
    storage: BackupStorage,
    clock: Clock | None = None,
) -> BackupExpireResult:
    if not isinstance(storage, BackupStorage):
        raise TypeError("Backup storage is required")
    active_clock = clock or SystemClock()
    try:
        record = BackupRecord.objects.get(pk=backup_id)
    except BackupRecord.DoesNotExist:
        raise BackupError(
            "operations.backup_not_found.v1", "备份记录不存在。"
        ) from None
    if record.state == BackupRecord.State.EXPIRED:
        return BackupExpireResult(record.id, record.state, False)
    if record.state != BackupRecord.State.COMPLETED:
        return BackupExpireResult(record.id, record.state, False)
    if record.expires_at is None or record.expires_at > active_clock.now():
        return BackupExpireResult(record.id, record.state, False)
    try:
        removed = storage.delete_archive(record.archive_key)
    except OSError:
        raise BackupRetryable("operations.backup_expiry_cleanup_failed.v1") from None
    with transaction.atomic():
        locked = BackupRecord.objects.select_for_update().get(pk=record.id)
        if locked.state == BackupRecord.State.EXPIRED:
            return BackupExpireResult(locked.id, locked.state, removed)
        if (
            locked.state != BackupRecord.State.COMPLETED
            or locked.expires_at is None
            or locked.expires_at > active_clock.now()
        ):
            raise BackupRetryable("operations.backup_state_changed.v1")
        locked.state = BackupRecord.State.EXPIRED
        locked.archive_key = ""
        locked.expired_at = active_clock.now()
        locked.heartbeat_at = locked.expired_at
        locked.save(
            update_fields=(
                "state",
                "archive_key",
                "expired_at",
                "heartbeat_at",
            )
        )
        return BackupExpireResult(locked.id, locked.state, removed)


def mark_backup_task_final_failed(
    *,
    week_id: str,
    error_code: str,
    storage: BackupStorage,
    clock: Clock | None = None,
) -> BackupFailureResult | None:
    normalized_week = _week_id(week_id)
    failure_code = _safe_error_code(error_code)
    active_clock = clock or SystemClock()
    record = BackupRecord.objects.filter(
        week_id=normalized_week,
        destination="local",
    ).first()
    if record is None:
        return None
    if record.state != BackupRecord.State.RUNNING:
        return BackupFailureResult(record.id, record.state)
    try:
        storage.cleanup_attempts(record.id)
        orphan_key = storage.archive_key(record.id)
        if storage.archive_exists(orphan_key):
            storage.delete_archive(orphan_key)
    except OSError:
        raise BackupRetryable("operations.backup_failure_cleanup_failed.v1") from None
    with transaction.atomic():
        locked = BackupRecord.objects.select_for_update().get(pk=record.id)
        if locked.state != BackupRecord.State.RUNNING:
            return BackupFailureResult(locked.id, locked.state)
        now = active_clock.now()
        locked.state = BackupRecord.State.FAILED
        locked.completed_at = now
        locked.error_code = failure_code
        locked.heartbeat_at = now
        locked.lease_token = None
        locked.lease_expires_at = None
        locked.save(
            update_fields=(
                "state",
                "completed_at",
                "error_code",
                "heartbeat_at",
                "lease_token",
                "lease_expires_at",
            )
        )
        return BackupFailureResult(locked.id, locked.state)
