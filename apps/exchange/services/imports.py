from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePath, PurePosixPath
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.exchange.formats import ArchiveError, MarkdownParseError, extract_zip
from apps.exchange.formats.markdown import parse_markdown
from apps.exchange.limits import DEFAULT_IMPORT_LIMITS, ImportLimits
from apps.exchange.models import ImportItem, ImportJob
from apps.exchange.staging import ImportStaging, ImportStagingError

AuthorCheck = Callable[[UUID], bool]
MarkdownRenderer = Callable[[str], str]
ImageValidator = Callable[[bytes], "ImportImage"]
_MAX_IMAGE_BYTES = 2 * 1024 * 1024


class ImportPreviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ImportImage:
    content: bytes
    detected_mime: str
    extension: str
    width: int
    height: int
    frame_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ImportPreviewResult:
    job_id: str
    status: str
    item_count: int
    valid_count: int
    invalid_count: int
    preview_version: int


@dataclass(frozen=True, slots=True)
class _ItemData:
    ordinal: int
    item_key: str
    item_path: str
    imported_article_id: str | None
    title: str
    parse_status: str
    classification: str | None
    front_matter: dict[str, object]
    body: str
    preview_html: str
    image_manifest: list[dict[str, object]]
    error_code: str


def _actor_id(value: UUID | str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ImportPreviewError(
            "exchange.import_author_required.v1",
            "只有启用的作者可以导入文章。",
        ) from None


def _source_name(value: str) -> str:
    if not isinstance(value, str):
        raise ImportPreviewError(
            "exchange.import_source_invalid.v1", "导入文件信息不合法。"
        )
    name = PurePath(value.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", name)
    cleaned = "".join(character for character in normalized if character.isprintable())
    if not cleaned:
        raise ImportPreviewError(
            "exchange.import_source_invalid.v1", "导入文件信息不合法。"
        )
    return cleaned[:255]


def _source_kind(value: str) -> ImportJob.SourceKind:
    try:
        return ImportJob.SourceKind(value)
    except (TypeError, ValueError):
        raise ImportPreviewError(
            "exchange.import_source_invalid.v1", "只支持 Markdown 或 ZIP 导入。"
        ) from None


def _fail_job(job: ImportJob, code: str) -> None:
    ImportJob.objects.filter(pk=job.id).update(
        status=ImportJob.Status.FAILED,
        error_code=code,
        preview_summary={},
    )


def _relative_path(path: Path, root: Path) -> str:
    try:
        relative = path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        raise ImportPreviewError(
            "exchange.archive_path_unsafe.v1", "导入包包含不安全路径。"
        ) from None
    return PurePosixPath(*relative.parts).as_posix()


def _read_markdown(path: Path) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError
        return path.read_bytes()
    except OSError:
        raise MarkdownParseError("exchange.import_markdown_invalid.v1") from None


def _image_manifest(
    *,
    job_id: str,
    markdown_path: Path,
    package_root: Path,
    image_references: tuple[tuple[str, str], ...],
    validator: ImageValidator,
    staging: ImportStaging,
) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []
    for source_path, purpose in image_references:
        candidate = markdown_path.parent.joinpath(*PurePosixPath(source_path).parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(package_root.resolve(strict=True))
            if resolved.is_symlink() or not resolved.is_file():
                raise OSError
            if resolved.stat().st_size > _MAX_IMAGE_BYTES:
                raise OSError
            validated = validator(resolved.read_bytes())
        except (OSError, TypeError, ValueError):
            raise MarkdownParseError("exchange.import_image_invalid.v1") from None
        if not isinstance(validated, ImportImage):
            raise TypeError("Image validator must return ImportImage")
        staging_key = staging.store_preview_image(
            job_id,
            digest=validated.sha256,
            extension=validated.extension,
            content=validated.content,
        )
        manifest.append(
            {
                "source_path": _relative_path(resolved, package_root),
                "reference": source_path,
                "purpose": purpose,
                "staging_key": staging_key,
                "sha256": validated.sha256,
                "detected_mime": validated.detected_mime,
                "width": validated.width,
                "height": validated.height,
                "frame_count": validated.frame_count,
            }
        )
    return manifest


def _invalid_item(
    *,
    ordinal: int,
    item_path: str,
    raw: bytes,
    error_code: str,
    title: str | None = None,
    metadata: dict[str, object] | None = None,
) -> _ItemData:
    return _ItemData(
        ordinal=ordinal,
        item_key=_item_key(item_path, raw),
        item_path=item_path,
        imported_article_id=None,
        title=(title or PurePosixPath(item_path).stem)[:255],
        parse_status=ImportItem.ParseStatus.INVALID,
        classification=ImportItem.Classification.INVALID,
        front_matter=metadata or {},
        body="",
        preview_html="",
        image_manifest=[],
        error_code=error_code,
    )


def _item_key(item_path: str, raw: bytes) -> str:
    digest = sha256()
    digest.update(item_path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(raw)
    return digest.hexdigest()


def _parse_item(
    *,
    ordinal: int,
    item_path: str,
    markdown_path: Path,
    package_root: Path,
    job_id: str,
    limits: ImportLimits,
    renderer: MarkdownRenderer,
    image_validator: ImageValidator,
    staging: ImportStaging,
) -> _ItemData:
    raw = _read_markdown(markdown_path)
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _invalid_item(
            ordinal=ordinal,
            item_path=item_path,
            raw=raw,
            error_code="exchange.import_markdown_invalid.v1",
        )
    try:
        document = parse_markdown(
            source,
            item_path=item_path,
            body_max_bytes=limits.body_bytes,
            renderer=renderer,
        )
        manifest = _image_manifest(
            job_id=job_id,
            markdown_path=markdown_path,
            package_root=package_root,
            image_references=tuple((path, "BODY") for path in document.body_image_paths)
            + (
                ((document.cover_image_path, "COVER"),)
                if document.cover_image_path
                else ()
            ),
            validator=image_validator,
            staging=staging,
        )
    except MarkdownParseError as exc:
        metadata = document.metadata if "document" in locals() else {}
        title = document.title if "document" in locals() else None
        return _invalid_item(
            ordinal=ordinal,
            item_path=item_path,
            raw=raw,
            error_code=exc.code,
            title=title,
            metadata=metadata,
        )
    return _ItemData(
        ordinal=ordinal,
        item_key=_item_key(item_path, raw),
        item_path=item_path,
        imported_article_id=document.imported_article_id,
        title=document.title,
        parse_status=ImportItem.ParseStatus.VALID,
        classification=None,
        front_matter=document.metadata,
        body=document.body,
        preview_html=document.preview_html,
        image_manifest=manifest,
        error_code="",
    )


def _create_item(job: ImportJob, item: _ItemData) -> None:
    invalid = item.parse_status == ImportItem.ParseStatus.INVALID
    ImportItem.objects.create(
        job=job,
        ordinal=item.ordinal,
        item_key=item.item_key,
        item_path=item.item_path,
        imported_article_id=item.imported_article_id,
        detected_title=item.title,
        parse_status=item.parse_status,
        classification=item.classification,
        decision=ImportItem.Decision.SKIP if invalid else None,
        included=not invalid,
        front_matter=item.front_matter,
        body_markdown=item.body,
        preview_html=item.preview_html,
        image_manifest=item.image_manifest,
        parse_error_code=item.error_code,
    )


def _error(code: str) -> ImportPreviewError:
    messages = {
        "exchange.import_compressed_limit.v1": "导入压缩包不能超过 64 MiB。",
        "exchange.archive_path_unsafe.v1": "导入包包含不安全路径。",
        "exchange.archive_entry_unsafe.v1": "导入包包含链接或设备文件。",
        "exchange.archive_expanded_limit.v1": "导入包展开后超过安全上限。",
        "exchange.archive_item_limit.v1": "导入包项目数量超过安全上限。",
        "exchange.archive_depth_limit.v1": "导入包目录层级超过安全上限。",
        "exchange.archive_ratio_limit.v1": "导入包压缩比超过安全上限。",
        "exchange.archive_invalid.v1": "导入压缩包无法安全读取。",
        "exchange.import_no_markdown.v1": "导入包中没有 Markdown 文章。",
        "exchange.import_staging_failed.v1": "导入文件暂存失败，请重试。",
    }
    return ImportPreviewError(code, messages.get(code, "导入预览创建失败。"))


def create_import_preview(
    *,
    actor_id: UUID | str,
    source_name: str,
    source_kind: str,
    chunks: Iterable[bytes],
    staging: ImportStaging,
    author_check: AuthorCheck,
    markdown_renderer: MarkdownRenderer,
    image_validator: ImageValidator,
    limits: ImportLimits = DEFAULT_IMPORT_LIMITS,
) -> ImportPreviewResult:
    actor = _actor_id(actor_id)
    if not isinstance(staging, ImportStaging) or not isinstance(limits, ImportLimits):
        raise TypeError("Import staging and limits are required")
    if not all(
        callable(port) for port in (author_check, markdown_renderer, image_validator)
    ):
        raise TypeError("Import integration ports must be callable")
    if not author_check(actor):
        raise ImportPreviewError(
            "exchange.import_author_required.v1",
            "只有启用的作者可以导入文章。",
        )
    normalized_name = _source_name(source_name)
    normalized_kind = _source_kind(source_kind)
    job = ImportJob.objects.create(
        author_id=actor,
        source_kind=normalized_kind,
        source_name=normalized_name,
    )
    try:
        source_limit = (
            limits.compressed_bytes
            if normalized_kind == ImportJob.SourceKind.ZIP
            else limits.body_bytes + 64 * 1024
        )
        try:
            source_path = staging.stage_source(
                job.id,
                chunks,
                max_bytes=source_limit,
            )
        except ImportStagingError:
            code = (
                "exchange.import_compressed_limit.v1"
                if normalized_kind == ImportJob.SourceKind.ZIP
                else "exchange.import_staging_failed.v1"
            )
            raise _error(code) from None

        if normalized_kind == ImportJob.SourceKind.ZIP:
            package_root = staging.extraction_root(job.id)
            try:
                extracted = extract_zip(source_path, package_root, limits=limits)
            except ArchiveError as exc:
                raise _error(exc.code) from None
            markdown_paths = sorted(
                (path for path in extracted if path.suffix.casefold() == ".md"),
                key=lambda path: _relative_path(path, package_root),
            )
        else:
            package_root = source_path.parent
            markdown_paths = [source_path]

        if not markdown_paths:
            raise _error("exchange.import_no_markdown.v1")
        valid = 0
        invalid = 0
        with transaction.atomic():
            for ordinal, markdown_path in enumerate(markdown_paths, start=1):
                item_path = (
                    normalized_name
                    if normalized_kind == ImportJob.SourceKind.MARKDOWN
                    else _relative_path(markdown_path, package_root)
                )
                item = _parse_item(
                    ordinal=ordinal,
                    item_path=item_path,
                    markdown_path=markdown_path,
                    package_root=package_root,
                    job_id=job.id,
                    limits=limits,
                    renderer=markdown_renderer,
                    image_validator=image_validator,
                    staging=staging,
                )
                _create_item(job, item)
                if item.parse_status == ImportItem.ParseStatus.VALID:
                    valid += 1
                else:
                    invalid += 1
        staging.cleanup_source(job.id)
        summary = {"invalid": invalid, "total": valid + invalid, "valid": valid}
        previewed_at = timezone.now()
        ImportJob.objects.filter(pk=job.id).update(
            status=ImportJob.Status.PREVIEW_READY,
            preview_summary=summary,
            previewed_at=previewed_at,
        )
        return ImportPreviewResult(
            job_id=job.id,
            status=ImportJob.Status.PREVIEW_READY,
            item_count=valid + invalid,
            valid_count=valid,
            invalid_count=invalid,
            preview_version=job.preview_version,
        )
    except ImportPreviewError as exc:
        ImportItem.objects.filter(job=job).delete()
        _fail_job(job, exc.code)
        try:
            staging.cleanup_job(job.id)
        except ImportStagingError:
            pass
        raise
    except Exception:
        ImportItem.objects.filter(job=job).delete()
        _fail_job(job, "exchange.import_preview_failed.v1")
        try:
            staging.cleanup_job(job.id)
        except ImportStagingError:
            pass
        raise _error("exchange.import_preview_failed.v1") from None
