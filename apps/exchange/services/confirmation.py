from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.core.ids import new_ulid, normalize_ulid

from ..models import ImportItem, ImportJob

AuthorCheck = Callable[[UUID], bool]
AuditWriter = Callable[..., object]
ImportDispatcher = Callable[[str, int], object]


class ImportConfirmationError(ValueError):
    def __init__(self, code: str, message: str = "导入确认失败。") -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ImportConfirmationResult:
    job_id: str
    preview_version: int
    status: str
    selected_count: int
    skipped_count: int
    already_confirmed: bool


def _actor(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ImportConfirmationError("exchange.import_not_found.v1") from None


def _job(value: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ImportConfirmationError("exchange.import_not_found.v1") from None


def _version(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImportConfirmationError("exchange.import_preview_conflict.v1")
    return value


def _counts(job: ImportJob) -> tuple[int, int]:
    selected = job.items.filter(
        parse_status=ImportItem.ParseStatus.VALID,
        included=True,
        decision__in=(ImportItem.Decision.CREATE, ImportItem.Decision.UPDATE),
    ).count()
    return selected, job.items.count() - selected


def confirm_import(
    *,
    actor_id,
    job_id: str,
    expected_preview_version: int,
    trace_code: str,
    client_ip: str,
    author_check: AuthorCheck,
    audit_writer: AuditWriter,
    dispatcher: ImportDispatcher,
) -> ImportConfirmationResult:
    actor = _actor(actor_id)
    identity = _job(job_id)
    version = _version(expected_preview_version)
    if not all(callable(port) for port in (author_check, audit_writer, dispatcher)):
        raise TypeError("Import confirmation ports are required")
    if not author_check(actor):
        raise ImportConfirmationError("exchange.import_author_required.v1")

    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update()
            .filter(pk=identity, author_id=actor)
            .first()
        )
        if job is None:
            raise ImportConfirmationError("exchange.import_not_found.v1")
        if job.confirmed_preview_version is not None:
            if job.confirmed_preview_version != version:
                raise ImportConfirmationError("exchange.import_preview_conflict.v1")
            selected, skipped = _counts(job)
            return ImportConfirmationResult(
                job.id,
                version,
                job.status,
                selected,
                skipped,
                True,
            )
        if (
            job.status != ImportJob.Status.PREVIEW_READY
            or job.preview_version != version
        ):
            raise ImportConfirmationError("exchange.import_preview_conflict.v1")

        items = list(job.items.select_for_update().order_by("ordinal"))
        selected = 0
        for item in items:
            if (
                item.parse_status != ImportItem.ParseStatus.VALID
                or not item.included
                or item.decision
                not in (ImportItem.Decision.CREATE, ImportItem.Decision.UPDATE)
            ):
                continue
            selected += 1
            if item.decision == ImportItem.Decision.CREATE:
                item.planned_article_id = (
                    item.imported_article_id
                    if item.classification == ImportItem.Classification.NEW
                    and item.imported_article_id is not None
                    else new_ulid()
                )
                item.save(update_fields=("planned_article_id",))
        skipped = len(items) - selected
        job.confirmed_preview_version = version
        job.confirmed_at = timezone.now()
        job.status = ImportJob.Status.PROCESSING
        job.result_summary = {}
        job.error_code = ""
        job.save(
            update_fields=(
                "confirmed_preview_version",
                "confirmed_at",
                "status",
                "result_summary",
                "error_code",
            )
        )
        audit_writer(
            action="exchange.import.confirmed",
            actor_id=actor,
            target_id=job.id,
            trace_code=trace_code,
            client_ip=client_ip,
            before={"preview_version": version},
            after={
                "preview_version": version,
                "selected_count": selected,
                "skipped_count": skipped,
            },
            summary="Confirm article import",
        )
        transaction.on_commit(lambda: dispatcher(job.id, version))
    return ImportConfirmationResult(
        job.id,
        version,
        job.status,
        selected,
        skipped,
        False,
    )
