from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from types import MappingProxyType
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid

from ..events import IMPORT_TITLE_WARNING
from ..models import ImportItem, ImportJob
from ..staging import ImportStaging, ImportStagingError

_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")


class ImportProcessingError(ValueError):
    def __init__(self, code: str, message: str = "导入条目处理失败。") -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


class ImportProcessingRetryable(RuntimeError):
    error_code = "exchange.import_processing_retryable.v1"


@dataclass(frozen=True, slots=True)
class ImportContentCommand:
    import_key: str
    operation: str
    article_id: str
    title: str
    body_markdown: str
    visibility: str
    summary_mode: str
    custom_summary: str | None
    section_id: UUID | None
    tag_ids: tuple[UUID, ...]
    proposed_tag_names: tuple[str, ...]
    cover_asset_id: str | None
    body_asset_ids: tuple[str, ...]
    comments_enabled: bool
    comments_view_login: bool
    comments_post_login: bool
    publication_status: str
    scheduled_for: object
    published_at: object


@dataclass(frozen=True, slots=True)
class ImportContentResult:
    article_id: str
    revision_id: str
    publication_status: str


@dataclass(frozen=True, slots=True)
class ImportMediaResult:
    asset_id: str
    purpose: str


@dataclass(frozen=True, slots=True)
class ImportProcessingResult:
    job_id: str
    preview_version: int
    status: str
    summary: Mapping[str, int]


ContentWriter = Callable[..., ImportContentResult]
ExistingContentResult = Callable[..., ImportContentResult | None]
MediaCreator = Callable[..., ImportMediaResult]
MediaCleanup = Callable[..., object]
WarningRecipient = Callable[[], UUID | None]


def _front_text(metadata: Mapping[str, object], key: str, default: str) -> str:
    value = metadata.get(key, default)
    if not isinstance(value, str):
        raise ImportProcessingError(f"content.import_{key}_invalid.v1")
    return value.upper() if key in {"visibility", "summary_mode", "status"} else value


def _front_bool(metadata: Mapping[str, object], key: str, default: bool) -> bool:
    value = metadata.get(key, default)
    if type(value) is not bool:
        raise ImportProcessingError("content.import_comments_invalid.v1")
    return value


def _rewrite_body(
    body: str,
    replacements: tuple[tuple[str, str], ...],
) -> str:
    rewritten = body
    for reference, asset_id in replacements:
        escaped = re.escape(reference)
        inline = re.compile(rf"(!\[[^\]\n]*\]\(\s*<?){escaped}(>?)(?=\s|\))")
        definition = re.compile(rf"(?m)^(\s*\[[^\]\n]+\]:\s*<?){escaped}(>?)(?=\s|$)")
        rewritten, inline_count = inline.subn(
            lambda match, target=asset_id: (
                f"{match.group(1)}media:{target}{match.group(2)}"
            ),
            rewritten,
        )
        rewritten, definition_count = definition.subn(
            lambda match, target=asset_id: (
                f"{match.group(1)}media:{target}{match.group(2)}"
            ),
            rewritten,
        )
        if inline_count + definition_count == 0:
            raise ImportProcessingError("exchange.import_image_reference_invalid.v1")
    return rewritten


def _reason_code(error: Exception) -> str:
    code = getattr(error, "code", "")
    return (
        code
        if isinstance(code, str) and _ERROR_CODE.fullmatch(code)
        else "exchange.import_item_failed.v1"
    )


def _needs_warning(item: ImportItem) -> bool:
    return (
        item.classification == ImportItem.Classification.TITLE_WARNING
        and item.decision == ImportItem.Decision.CREATE
        and item.conflict_summary.get("owner_scope") in {"FOREIGN", "MIXED"}
        and str(item.front_matter.get("status", "DRAFT")).upper()
        in {"PUBLISHED", "SCHEDULED"}
    )


def _manifest_entry(value: object) -> dict[str, object]:
    fields = {
        "source_path",
        "reference",
        "purpose",
        "staging_key",
        "sha256",
        "detected_mime",
        "width",
        "height",
        "frame_count",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ImportProcessingError("exchange.import_image_manifest_invalid.v1")
    if value["purpose"] not in {"BODY", "COVER"} or not all(
        isinstance(value[field], str)
        for field in (
            "source_path",
            "reference",
            "staging_key",
            "sha256",
            "detected_mime",
        )
    ):
        raise ImportProcessingError("exchange.import_image_manifest_invalid.v1")
    return value


def _content_command(
    *,
    item: ImportItem,
    body_markdown: str,
    cover_asset_id: str | None,
    body_asset_ids: tuple[str, ...],
) -> ImportContentCommand:
    metadata = item.front_matter
    if not isinstance(metadata, dict):
        raise ImportProcessingError("exchange.front_matter_invalid.v1")
    operation = item.decision or ""
    article_id = (
        item.planned_article_id
        if operation == ImportItem.Decision.CREATE
        else item.target_article_id
    )
    if article_id is None:
        raise ImportProcessingError("exchange.import_target_invalid.v1")
    summary = metadata.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise ImportProcessingError("content.import_summary_invalid.v1")
    summary_mode = _front_text(
        metadata,
        "summary_mode",
        "CUSTOM" if summary else "AUTO",
    )
    return ImportContentCommand(
        import_key=f"import:{item.job_id}:{item.id}",
        operation=operation,
        article_id=article_id,
        title=item.detected_title,
        body_markdown=body_markdown,
        visibility=_front_text(metadata, "visibility", "PUBLIC"),
        summary_mode=summary_mode,
        custom_summary=summary if summary_mode == "CUSTOM" else None,
        section_id=item.mapped_section_id,
        tag_ids=tuple(UUID(value) for value in item.mapped_tag_ids),
        proposed_tag_names=tuple(item.proposed_tag_names),
        cover_asset_id=cover_asset_id,
        body_asset_ids=body_asset_ids,
        comments_enabled=_front_bool(metadata, "comments_enabled", True),
        comments_view_login=_front_bool(metadata, "comments_view_login", False),
        comments_post_login=_front_bool(metadata, "comments_post_login", False),
        publication_status=_front_text(metadata, "status", "DRAFT"),
        scheduled_for=metadata.get("scheduled_for"),
        published_at=metadata.get("published_at"),
    )


def _mark_terminal(
    *,
    item_id: str,
    status: str,
    reason_code: str,
    result: ImportContentResult | None = None,
    warning_recipient_id: UUID | None = None,
    actor_id: UUID | None = None,
    trace_code: str | None = None,
) -> None:
    with transaction.atomic():
        item = (
            ImportItem.objects.select_for_update().select_related("job").get(pk=item_id)
        )
        if item.result_status != ImportItem.ResultStatus.PENDING:
            return
        item.result_status = status
        item.result_reason_code = reason_code
        item.result_article_id = result.article_id if result else None
        item.result_revision_id = result.revision_id if result else None
        item.save(
            update_fields=(
                "result_status",
                "result_reason_code",
                "result_article_id",
                "result_revision_id",
            )
        )
        if warning_recipient_id is not None and result is not None:
            enqueue_event(
                IMPORT_TITLE_WARNING,
                aggregate_type="article",
                aggregate_id=result.article_id,
                actor_id=actor_id,
                trace_code=trace_code,
                payload={
                    "job_id": item.job_id,
                    "item_id": item.id,
                    "recipient_id": str(warning_recipient_id),
                },
            )


def _process_selected_item(
    *,
    item: ImportItem,
    actor_id: UUID,
    trace_code: str,
    staging: ImportStaging,
    content_writer: ContentWriter,
    existing_result: ExistingContentResult,
    media_creator: MediaCreator,
    media_cleanup: MediaCleanup,
    warning_recipient_id: UUID | None,
) -> None:
    import_key = f"import:{item.job_id}:{item.id}"
    recovered = existing_result(actor_id=actor_id, import_key=import_key)
    if recovered is not None:
        _mark_terminal(
            item_id=item.id,
            status=ImportItem.ResultStatus.SUCCESS,
            reason_code=(
                "exchange.import_created.v1"
                if item.decision == ImportItem.Decision.CREATE
                else "exchange.import_updated.v1"
            ),
            result=recovered,
            warning_recipient_id=warning_recipient_id,
            actor_id=actor_id,
            trace_code=trace_code,
        )
        return

    article_id = (
        item.planned_article_id
        if item.decision == ImportItem.Decision.CREATE
        else item.target_article_id
    )
    if article_id is None:
        raise ImportProcessingError("exchange.import_target_invalid.v1")
    created_assets: list[str] = []
    body_assets: list[str] = []
    replacements: list[tuple[str, str]] = []
    cover_asset_id = None
    try:
        for raw_entry in item.image_manifest:
            entry = _manifest_entry(raw_entry)
            content = staging.read_preview_image(
                item.job_id,
                staging_key=str(entry["staging_key"]),
                digest=str(entry["sha256"]),
            )
            media = media_creator(
                owner_id=actor_id,
                article_id=article_id,
                purpose=str(entry["purpose"]),
                original_name=PurePosixPath(str(entry["source_path"])).name,
                content=content,
            )
            created_assets.append(media.asset_id)
            if media.purpose == "BODY":
                body_assets.append(media.asset_id)
                replacements.append((str(entry["reference"]), media.asset_id))
            else:
                if cover_asset_id is not None:
                    raise ImportProcessingError("exchange.import_cover_invalid.v1")
                cover_asset_id = media.asset_id
        rewritten = _rewrite_body(item.body_markdown, tuple(replacements))
        command = _content_command(
            item=item,
            body_markdown=rewritten,
            cover_asset_id=cover_asset_id,
            body_asset_ids=tuple(body_assets),
        )
        result = content_writer(
            actor_id=actor_id,
            command=command,
            trace_code=trace_code,
        )
    except Exception:
        if created_assets:
            media_cleanup(owner_id=actor_id, asset_ids=tuple(created_assets))
        raise
    _mark_terminal(
        item_id=item.id,
        status=ImportItem.ResultStatus.SUCCESS,
        reason_code=(
            "exchange.import_created.v1"
            if item.decision == ImportItem.Decision.CREATE
            else "exchange.import_updated.v1"
        ),
        result=result,
        warning_recipient_id=warning_recipient_id,
        actor_id=actor_id,
        trace_code=trace_code,
    )


def _finalize_job(job_id: str, preview_version: int) -> ImportProcessingResult:
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().get(pk=job_id)
        if job.confirmed_preview_version != preview_version:
            raise ImportProcessingError("exchange.import_preview_conflict.v1")
        counts = {
            status: job.items.filter(result_status=status).count()
            for status in (
                ImportItem.ResultStatus.SUCCESS,
                ImportItem.ResultStatus.SKIPPED,
                ImportItem.ResultStatus.FAILED,
                ImportItem.ResultStatus.PENDING,
            )
        }
        if counts[ImportItem.ResultStatus.PENDING]:
            raise ImportProcessingRetryable
        summary = {
            "failed": counts[ImportItem.ResultStatus.FAILED],
            "skipped": counts[ImportItem.ResultStatus.SKIPPED],
            "success": counts[ImportItem.ResultStatus.SUCCESS],
        }
        if summary["failed"] and not summary["success"]:
            status = ImportJob.Status.FAILED
            error_code = "exchange.import_all_items_failed.v1"
        elif summary["failed"] or (summary["skipped"] and summary["success"]):
            status = ImportJob.Status.PARTIAL
            error_code = ""
        else:
            status = ImportJob.Status.COMPLETED
            error_code = ""
        job.status = status
        job.error_code = error_code
        job.result_summary = summary
        job.completed_at = timezone.now()
        job.save(
            update_fields=(
                "status",
                "error_code",
                "result_summary",
                "completed_at",
            )
        )
    return ImportProcessingResult(
        job.id,
        preview_version,
        job.status,
        MappingProxyType(summary),
    )


def mark_import_job_final_failed(
    *,
    job_id: str,
    preview_version: int,
    error_code: str,
    completed_at,
) -> bool:
    if not isinstance(job_id, str):
        raise ValueError("Invalid import job ID")
    try:
        normalized_job_id = normalize_ulid(job_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid import job ID") from None
    if (
        isinstance(preview_version, bool)
        or not isinstance(preview_version, int)
        or preview_version < 1
        or not isinstance(error_code, str)
        or _ERROR_CODE.fullmatch(error_code) is None
    ):
        raise ValueError("Invalid import failure state")
    if not isinstance(completed_at, datetime) or completed_at.tzinfo is None:
        raise ValueError("completed_at must be timezone-aware")

    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update()
            .filter(
                pk=normalized_job_id,
                confirmed_preview_version=preview_version,
            )
            .first()
        )
        if job is None or job.status in {
            ImportJob.Status.COMPLETED,
            ImportJob.Status.PARTIAL,
            ImportJob.Status.FAILED,
        }:
            return False
        job.items.filter(result_status=ImportItem.ResultStatus.PENDING).update(
            result_status=ImportItem.ResultStatus.FAILED,
            result_reason_code=error_code,
        )
        counts = {
            status: job.items.filter(result_status=status).count()
            for status in (
                ImportItem.ResultStatus.SUCCESS,
                ImportItem.ResultStatus.SKIPPED,
                ImportItem.ResultStatus.FAILED,
            )
        }
        job.status = ImportJob.Status.FAILED
        job.error_code = error_code
        job.result_summary = {
            "failed": counts[ImportItem.ResultStatus.FAILED],
            "skipped": counts[ImportItem.ResultStatus.SKIPPED],
            "success": counts[ImportItem.ResultStatus.SUCCESS],
        }
        job.completed_at = completed_at
        job.save(
            update_fields=(
                "status",
                "error_code",
                "result_summary",
                "completed_at",
            )
        )
    return True


def process_import_job(
    *,
    job_id: str,
    preview_version: int,
    staging: ImportStaging,
    content_writer: ContentWriter,
    existing_result: ExistingContentResult,
    media_creator: MediaCreator,
    media_cleanup: MediaCleanup,
    warning_recipient: WarningRecipient,
    trace_code: str,
) -> ImportProcessingResult:
    if not isinstance(staging, ImportStaging) or not all(
        callable(port)
        for port in (
            content_writer,
            existing_result,
            media_creator,
            media_cleanup,
            warning_recipient,
        )
    ):
        raise TypeError("Import processing ports are required")
    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update()
            .filter(pk=job_id, confirmed_preview_version=preview_version)
            .first()
        )
        if job is None:
            raise ImportProcessingError("exchange.import_not_found.v1")
        if job.status in {
            ImportJob.Status.COMPLETED,
            ImportJob.Status.PARTIAL,
            ImportJob.Status.FAILED,
        }:
            result = ImportProcessingResult(
                job.id,
                preview_version,
                job.status,
                MappingProxyType(dict(job.result_summary)),
            )
            terminal = True
        elif job.status != ImportJob.Status.PROCESSING:
            raise ImportProcessingError("exchange.import_state_invalid.v1")
        else:
            terminal = False
            result = None
            item_ids = tuple(job.items.order_by("ordinal").values_list("id", flat=True))
            actor_id = job.author_id

    if terminal:
        try:
            staging.cleanup_job(job_id)
        except ImportStagingError:
            raise ImportProcessingRetryable from None
        assert result is not None
        return result

    for item_id in item_ids:
        item = ImportItem.objects.select_related("job").get(pk=item_id)
        if item.result_status != ImportItem.ResultStatus.PENDING:
            continue
        if (
            item.parse_status != ImportItem.ParseStatus.VALID
            or not item.included
            or item.decision == ImportItem.Decision.SKIP
        ):
            _mark_terminal(
                item_id=item.id,
                status=ImportItem.ResultStatus.SKIPPED,
                reason_code=(
                    item.parse_error_code
                    if item.parse_error_code
                    else "exchange.import_skipped.v1"
                ),
            )
            continue
        recipient_id = None
        if _needs_warning(item):
            recipient_id = warning_recipient()
            if recipient_id is None or not isinstance(recipient_id, UUID):
                raise ImportProcessingRetryable
        try:
            _process_selected_item(
                item=item,
                actor_id=actor_id,
                trace_code=trace_code,
                staging=staging,
                content_writer=content_writer,
                existing_result=existing_result,
                media_creator=media_creator,
                media_cleanup=media_cleanup,
                warning_recipient_id=recipient_id,
            )
        except ImportProcessingRetryable:
            raise
        except Exception as exc:
            _mark_terminal(
                item_id=item.id,
                status=ImportItem.ResultStatus.FAILED,
                reason_code=_reason_code(exc),
            )

    result = _finalize_job(job_id, preview_version)
    try:
        staging.cleanup_job(job_id)
    except ImportStagingError:
        raise ImportProcessingRetryable from None
    return result
