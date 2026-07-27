import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from uuid import UUID

from django.db import transaction

from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.core.time.shanghai import shanghai_business_date

from ..archive_storage import ExportArchiveStorage
from ..events import EXPORT_AUTHOR_CONTENT, EXPORT_COMPLETED
from ..formats import write_export_zip
from ..models import ExportJob

AdministratorCheck = Callable[[UUID], bool]
AuditWriter = Callable[..., object]
Heartbeat = Callable[[], object]
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")
_JOB_LEASE_SECONDS = 600
_RETENTION = timedelta(days=3)


class ExportLifecycleError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class ExportBuildRetryable(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = _error_code(error_code)
        super().__init__(self.error_code)


class _ExportCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExportBuildResult:
    job_id: str
    state: str
    archive_size_bytes: int | None
    archive_sha256: str
    article_count: int
    revision_count: int
    media_count: int


@dataclass(frozen=True, slots=True)
class ExportCancelResult:
    job_id: str
    state: str


@dataclass(frozen=True, slots=True)
class ExportDownloadGrant:
    job_id: str
    archive_key: str
    download_name: str
    size_bytes: int
    sha256: str
    content_type: str = "application/zip"


@dataclass(frozen=True, slots=True)
class ExportExpireResult:
    job_id: str
    state: str
    removed: bool


@dataclass(frozen=True, slots=True)
class ExportFailureResult:
    job_id: str
    state: str


def _job_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ExportLifecycleError(
            "exchange.export_not_found.v1", "导出任务不存在。"
        ) from None


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ExportLifecycleError(
            "exchange.export_admin_required.v1", "只有管理员可以操作导出任务。"
        ) from None


def _error_code(value: str) -> str:
    if not isinstance(value, str) or _ERROR_CODE.fullmatch(value) is None:
        return "exchange.export_build_failed.v1"
    return value


def _require_requesting_administrator(
    job: ExportJob,
    *,
    actor_id,
    administrator_check: AdministratorCheck,
) -> UUID:
    actor = _actor_id(actor_id)
    if not callable(administrator_check) or not administrator_check(actor):
        raise ExportLifecycleError(
            "exchange.export_admin_required.v1", "只有管理员可以操作导出任务。"
        )
    if job.requested_by_id != actor:
        raise ExportLifecycleError("exchange.export_not_found.v1", "导出任务不存在。")
    return actor


def _digest(stream) -> tuple[int, str]:
    digest = sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _cancelled_result(job: ExportJob) -> ExportBuildResult:
    return ExportBuildResult(job.id, job.state, None, "", 0, 0, 0)


def _completed_result(job: ExportJob) -> ExportBuildResult:
    return ExportBuildResult(
        job.id,
        job.state,
        job.archive_size_bytes,
        job.archive_sha256,
        int(job.selection_summary.get("selected_count", 0)),
        int(job.selection_summary.get("revision_count", 0)),
        int(job.selection_summary.get("media_count", 0)),
    )


def _finish_cancel(
    job_id: str,
    *,
    storage: ExportArchiveStorage,
    clock: Clock,
) -> ExportBuildResult:
    storage.discard_part(job_id)
    orphan_key = storage.archive_key(job_id)
    if storage.archive_exists(orphan_key):
        storage.delete_archive(orphan_key)
    with transaction.atomic():
        job = ExportJob.objects.select_for_update().get(pk=job_id)
        if job.state == ExportJob.State.CANCEL_REQUESTED:
            now = clock.now()
            job.state = ExportJob.State.CANCELLED
            job.cancelled_at = now
            job.heartbeat_at = now
            job.lease_expires_at = None
            job.save(
                update_fields=(
                    "state",
                    "cancelled_at",
                    "heartbeat_at",
                    "lease_expires_at",
                )
            )
        return _cancelled_result(job)


def _progress(
    job_id: str,
    *,
    heartbeat: Heartbeat,
    clock: Clock,
) -> None:
    if not callable(heartbeat):
        raise TypeError("Export heartbeat is required")
    state = ExportJob.objects.filter(pk=job_id).values_list("state", flat=True).first()
    if state in (ExportJob.State.CANCEL_REQUESTED, ExportJob.State.CANCELLED):
        raise _ExportCancelled
    if state != ExportJob.State.RUNNING:
        raise ExportBuildRetryable("exchange.export_state_changed.v1")
    heartbeat()
    now = clock.now()
    ExportJob.objects.filter(pk=job_id, state=ExportJob.State.RUNNING).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=_JOB_LEASE_SECONDS),
    )


def _prepare_build(
    job_id: str,
    *,
    storage: ExportArchiveStorage,
    clock: Clock,
) -> ExportBuildResult | tuple[ExportJob, tuple]:
    with transaction.atomic():
        job = (
            ExportJob.objects.select_for_update()
            .prefetch_related("selections")
            .get(pk=job_id)
        )
        if job.state == ExportJob.State.COMPLETED:
            return _completed_result(job)
        if job.state in (
            ExportJob.State.CANCELLED,
            ExportJob.State.FAILED,
            ExportJob.State.EXPIRED,
        ):
            return _cancelled_result(job)
        if job.state == ExportJob.State.CANCEL_REQUESTED:
            return job, ()
        now = clock.now()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=_JOB_LEASE_SECONDS)
        job.save(update_fields=("heartbeat_at", "lease_expires_at"))
        return job, tuple(job.selections.all())


def build_export_archive(
    *,
    job_id: str,
    storage: ExportArchiveStorage,
    revision_provider,
    media_index_provider,
    media_reader,
    heartbeat: Heartbeat = lambda: None,
    clock: Clock | None = None,
) -> ExportBuildResult:
    identity = _job_id(job_id)
    active_clock = clock or SystemClock()
    try:
        prepared = _prepare_build(identity, storage=storage, clock=active_clock)
    except ExportJob.DoesNotExist:
        raise ExportLifecycleError(
            "exchange.export_not_found.v1", "导出任务不存在。"
        ) from None
    if isinstance(prepared, ExportBuildResult):
        return prepared
    job, selections = prepared
    if job.state == ExportJob.State.CANCEL_REQUESTED:
        return _finish_cancel(identity, storage=storage, clock=active_clock)
    archive_key = storage.archive_key(identity)
    if storage.archive_exists(archive_key):
        storage.delete_archive(archive_key)
    storage.discard_part(identity)
    committed = False
    summary: dict[str, int] = {}
    try:
        with storage.open_part(identity) as stream:
            summary = write_export_zip(
                stream,
                job_id=identity,
                generated_at=active_clock.now(),
                selections=selections,
                revision_provider=revision_provider,
                media_index_provider=media_index_provider,
                media_reader=media_reader,
                progress=lambda: _progress(
                    identity, heartbeat=heartbeat, clock=active_clock
                ),
            )
            stream.flush()
            os.fsync(stream.fileno())
        _progress(identity, heartbeat=heartbeat, clock=active_clock)
        with storage.open_part_read(identity) as stream:
            archive_size, archive_sha = _digest(stream)
    except _ExportCancelled:
        return _finish_cancel(identity, storage=storage, clock=active_clock)
    except Exception as exc:
        storage.discard_part(identity)
        error_code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        raise ExportBuildRetryable(_error_code(error_code)) from None

    try:
        with transaction.atomic():
            locked = ExportJob.objects.select_for_update().get(pk=identity)
            if locked.state in (
                ExportJob.State.CANCEL_REQUESTED,
                ExportJob.State.CANCELLED,
            ):
                raise _ExportCancelled
            if locked.state == ExportJob.State.COMPLETED:
                storage.discard_part(identity)
                return _completed_result(locked)
            if locked.state != ExportJob.State.RUNNING:
                raise ExportBuildRetryable("exchange.export_state_changed.v1")
            archive_key = storage.commit_part(identity)
            committed = True
            now = active_clock.now()
            locked.state = ExportJob.State.COMPLETED
            locked.archive_key = archive_key
            locked.archive_size_bytes = archive_size
            locked.archive_sha256 = archive_sha
            locked.completed_at = now
            locked.expires_at = now + _RETENTION
            locked.heartbeat_at = now
            locked.lease_expires_at = None
            locked.selection_summary = {
                **locked.selection_summary,
                **summary,
            }
            locked.save(
                update_fields=(
                    "state",
                    "archive_key",
                    "archive_size_bytes",
                    "archive_sha256",
                    "completed_at",
                    "expires_at",
                    "heartbeat_at",
                    "lease_expires_at",
                    "selection_summary",
                )
            )
            enqueue_event(
                EXPORT_COMPLETED,
                aggregate_type="export_job",
                aggregate_id=locked.id,
                actor_id=locked.requested_by_id,
                payload={"recipient_id": str(locked.requested_by_id)},
                clock=active_clock,
            )
            export_date = shanghai_business_date(now).isoformat()
            author_ids = sorted(
                {
                    selection.author_id
                    for selection in locked.selections.all()
                    if selection.author_id != locked.requested_by_id
                },
                key=str,
            )
            for author_id in author_ids:
                enqueue_event(
                    EXPORT_AUTHOR_CONTENT,
                    aggregate_type="export_job",
                    aggregate_id=locked.id,
                    actor_id=locked.requested_by_id,
                    payload={
                        "recipient_id": str(author_id),
                        "export_date": export_date,
                    },
                    clock=active_clock,
                )
        return ExportBuildResult(
            identity,
            ExportJob.State.COMPLETED,
            archive_size,
            archive_sha,
            summary["article_count"],
            summary["revision_count"],
            summary["media_count"],
        )
    except _ExportCancelled:
        return _finish_cancel(identity, storage=storage, clock=active_clock)
    except Exception as exc:
        if committed:
            storage.delete_archive(archive_key)
        else:
            storage.discard_part(identity)
        if isinstance(exc, ExportBuildRetryable):
            raise
        error_code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
        raise ExportBuildRetryable(_error_code(error_code)) from None


def cancel_export(
    *,
    actor_id,
    job_id: str,
    trace_code: str,
    client_ip: str,
    storage: ExportArchiveStorage,
    administrator_check: AdministratorCheck,
    audit_writer: AuditWriter,
    clock: Clock | None = None,
) -> ExportCancelResult:
    identity = _job_id(job_id)
    if not callable(audit_writer):
        raise TypeError("Export cancellation audit writer is required")
    active_clock = clock or SystemClock()
    try:
        with transaction.atomic():
            job = ExportJob.objects.select_for_update().get(pk=identity)
            actor = _require_requesting_administrator(
                job,
                actor_id=actor_id,
                administrator_check=administrator_check,
            )
            if job.state == ExportJob.State.COMPLETED:
                raise ExportLifecycleError(
                    "exchange.export_already_completed.v1",
                    "导出已经完成，无法取消。",
                )
            if job.state == ExportJob.State.EXPIRED:
                raise ExportLifecycleError(
                    "exchange.export_expired.v1", "导出已经过期。"
                )
            if job.state in (ExportJob.State.CANCELLED, ExportJob.State.FAILED):
                return ExportCancelResult(job.id, job.state)
            if job.state == ExportJob.State.RUNNING:
                now = active_clock.now()
                job.state = ExportJob.State.CANCEL_REQUESTED
                job.cancel_requested_at = now
                job.heartbeat_at = now
                job.save(
                    update_fields=(
                        "state",
                        "cancel_requested_at",
                        "heartbeat_at",
                    )
                )
                audit_writer(
                    action="exchange.export.cancel_requested",
                    actor_id=actor,
                    target_id=job.id,
                    trace_code=trace_code,
                    client_ip=client_ip,
                    before={"state": ExportJob.State.RUNNING},
                    after={"state": ExportJob.State.CANCEL_REQUESTED},
                    summary="Administrator requested export cancellation",
                )
    except ExportJob.DoesNotExist:
        raise ExportLifecycleError(
            "exchange.export_not_found.v1", "导出任务不存在。"
        ) from None
    try:
        result = _finish_cancel(identity, storage=storage, clock=active_clock)
    except OSError:
        raise ExportLifecycleError(
            "exchange.export_cancel_cleanup_failed.v1",
            "导出取消清理失败，请稍后重试。",
        ) from None
    return ExportCancelResult(result.job_id, result.state)


def export_download(
    *,
    actor_id,
    job_id: str,
    trace_code: str,
    client_ip: str,
    storage: ExportArchiveStorage,
    administrator_check: AdministratorCheck,
    audit_writer: AuditWriter,
    clock: Clock | None = None,
) -> ExportDownloadGrant:
    identity = _job_id(job_id)
    if not callable(audit_writer):
        raise TypeError("Export download audit writer is required")
    active_clock = clock or SystemClock()
    try:
        job = ExportJob.objects.get(pk=identity)
    except ExportJob.DoesNotExist:
        raise ExportLifecycleError(
            "exchange.export_not_found.v1", "导出任务不存在。"
        ) from None
    actor = _require_requesting_administrator(
        job,
        actor_id=actor_id,
        administrator_check=administrator_check,
    )
    if job.state != ExportJob.State.COMPLETED:
        code = (
            "exchange.export_expired.v1"
            if job.state == ExportJob.State.EXPIRED
            else "exchange.export_not_ready.v1"
        )
        raise ExportLifecycleError(code, "导出文件当前不可下载。")
    if job.expires_at is None or job.expires_at <= active_clock.now():
        raise ExportLifecycleError("exchange.export_expired.v1", "导出文件已经过期。")
    try:
        with storage.open_archive(job.archive_key) as stream:
            size, digest = _digest(stream)
    except (FileNotFoundError, OSError):
        raise ExportLifecycleError(
            "exchange.export_file_missing.v1", "导出文件不存在。"
        ) from None
    if size != job.archive_size_bytes or digest != job.archive_sha256:
        raise ExportLifecycleError(
            "exchange.export_file_corrupt.v1", "导出文件校验失败。"
        )
    audit_writer(
        action="exchange.export.downloaded",
        actor_id=actor,
        target_id=job.id,
        trace_code=trace_code,
        client_ip=client_ip,
        before={},
        after={"state": job.state},
        summary="Administrator downloaded content export",
    )
    return ExportDownloadGrant(
        job.id,
        job.archive_key,
        f"kaj-export-{job.id}.zip",
        size,
        digest,
    )


def due_export_expiry_ids(
    *,
    batch_size: int = 100,
    clock: Clock | None = None,
) -> tuple[str, ...]:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= 1000
    ):
        raise ValueError("Export expiry batch size is invalid")
    now = (clock or SystemClock()).now()
    return tuple(
        ExportJob.objects.filter(
            state=ExportJob.State.COMPLETED,
            expires_at__lte=now,
        )
        .order_by("expires_at", "id")
        .values_list("id", flat=True)[:batch_size]
    )


def expire_export(
    *,
    job_id: str,
    storage: ExportArchiveStorage,
    clock: Clock | None = None,
) -> ExportExpireResult:
    identity = _job_id(job_id)
    active_clock = clock or SystemClock()
    try:
        job = ExportJob.objects.get(pk=identity)
    except ExportJob.DoesNotExist:
        raise ExportLifecycleError(
            "exchange.export_not_found.v1", "导出任务不存在。"
        ) from None
    if job.state == ExportJob.State.EXPIRED:
        return ExportExpireResult(job.id, job.state, False)
    if job.state != ExportJob.State.COMPLETED:
        return ExportExpireResult(job.id, job.state, False)
    if job.expires_at is None or job.expires_at > active_clock.now():
        return ExportExpireResult(job.id, job.state, False)
    try:
        removed = storage.delete_archive(job.archive_key)
    except OSError:
        raise ExportBuildRetryable("exchange.export_expiry_cleanup_failed.v1") from None
    with transaction.atomic():
        locked = ExportJob.objects.select_for_update().get(pk=identity)
        if locked.state == ExportJob.State.EXPIRED:
            return ExportExpireResult(locked.id, locked.state, removed)
        if (
            locked.state != ExportJob.State.COMPLETED
            or locked.expires_at is None
            or locked.expires_at > active_clock.now()
        ):
            raise ExportBuildRetryable("exchange.export_state_changed.v1")
        locked.state = ExportJob.State.EXPIRED
        locked.archive_key = ""
        locked.expired_at = active_clock.now()
        locked.heartbeat_at = locked.expired_at
        locked.lease_expires_at = None
        locked.save(
            update_fields=(
                "state",
                "archive_key",
                "expired_at",
                "heartbeat_at",
                "lease_expires_at",
            )
        )
        return ExportExpireResult(locked.id, locked.state, removed)


def mark_export_task_final_failed(
    *,
    job_id: str,
    error_code: str,
    storage: ExportArchiveStorage,
    clock: Clock | None = None,
) -> ExportFailureResult:
    identity = _job_id(job_id)
    failure_code = _error_code(error_code)
    active_clock = clock or SystemClock()
    try:
        state = (
            ExportJob.objects.filter(pk=identity).values_list("state", flat=True).get()
        )
    except ExportJob.DoesNotExist:
        raise ExportLifecycleError(
            "exchange.export_not_found.v1", "导出任务不存在。"
        ) from None
    if state == ExportJob.State.CANCEL_REQUESTED:
        cancelled = _finish_cancel(identity, storage=storage, clock=active_clock)
        return ExportFailureResult(cancelled.job_id, cancelled.state)
    if state != ExportJob.State.RUNNING:
        return ExportFailureResult(identity, state)
    try:
        storage.discard_part(identity)
        orphan_key = storage.archive_key(identity)
        if storage.archive_exists(orphan_key):
            storage.delete_archive(orphan_key)
    except OSError:
        raise ExportBuildRetryable(
            "exchange.export_failure_cleanup_failed.v1"
        ) from None
    cancel_won = False
    with transaction.atomic():
        job = ExportJob.objects.select_for_update().get(pk=identity)
        if job.state == ExportJob.State.CANCEL_REQUESTED:
            cancel_won = True
        elif job.state != ExportJob.State.RUNNING:
            return ExportFailureResult(job.id, job.state)
        else:
            now = active_clock.now()
            job.state = ExportJob.State.FAILED
            job.completed_at = now
            job.error_code = failure_code
            job.heartbeat_at = now
            job.lease_expires_at = None
            job.save(
                update_fields=(
                    "state",
                    "completed_at",
                    "error_code",
                    "heartbeat_at",
                    "lease_expires_at",
                )
            )
    if cancel_won:
        cancelled = _finish_cancel(identity, storage=storage, clock=active_clock)
        return ExportFailureResult(cancelled.job_id, cancelled.state)
    return ExportFailureResult(job.id, job.state)


def open_export_archive(
    grant: ExportDownloadGrant,
    *,
    storage: ExportArchiveStorage,
):
    if not isinstance(grant, ExportDownloadGrant):
        raise TypeError("Export download grant is required")
    return storage.open_archive(grant.archive_key)
