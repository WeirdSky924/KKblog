from collections.abc import Iterable
from functools import partial

from django.conf import settings

from apps.accounts.public import (
    active_administrator_id,
    is_active_author,
    is_administrator,
)
from apps.content.public import (
    ImportArticleCommand as ContentImportArticleCommand,
)
from apps.content.public import (
    ImportArticleError,
    ImportContentError,
    export_article_snapshots,
    export_revision_payloads,
)
from apps.content.public import (
    import_article_item as write_content_import_item,
)
from apps.content.public import (
    import_conflict_facts as content_import_conflict_facts,
)
from apps.content.public import (
    imported_article_result as content_imported_article_result,
)
from apps.content.public import (
    resolve_import_metadata as content_resolve_import_metadata,
)
from apps.content.public import (
    validate_import_mapping as content_validate_import_mapping,
)
from apps.core.observability.trace import new_trace_code
from apps.exchange.public import (
    ExportArchiveStorage,
    ImportConflictFacts,
    ImportContentCommand,
    ImportContentResult,
    ImportDecisionError,
    ImportImage,
    ImportLimits,
    ImportMediaResult,
    ImportMetadataMapping,
    ImportPreviewResult,
    ImportStaging,
    build_export_archive,
    cancel_export,
    classify_import_preview,
    confirm_import,
    create_import_preview,
    due_export_expiry_ids,
    expire_export,
    export_download,
    import_preview,
    mark_export_task_final_failed,
    open_export_archive,
    process_import_job,
    request_export,
    update_import_decision,
)
from apps.media.public import (
    MediaPurpose,
    export_revision_media,
    read_export_media,
    render_markdown,
)
from apps.media.public import (
    create_import_asset as create_media_import_asset,
)
from apps.media.public import (
    discard_import_assets as discard_media_import_assets,
)
from apps.media.public import (
    validate_import_image as validate_media_import_image,
)
from apps.media.storage import FilesystemMediaStorage
from apps.operations.public import record_audit_entry, require_image_creation_capacity


def active_import_author(actor_id) -> bool:
    return is_active_author(actor_id)


def render_import_markdown(source: str) -> str:
    return render_markdown(source).html


def validate_import_image(content: bytes) -> ImportImage:
    validated = validate_media_import_image(content)
    return ImportImage(
        content=validated.content,
        detected_mime=validated.detected_mime,
        extension=validated.extension,
        width=validated.width,
        height=validated.height,
        frame_count=validated.frame_count,
        sha256=validated.sha256,
    )


def import_conflict_facts(
    *, imported_article_id: str | None, title: str
) -> ImportConflictFacts:
    try:
        facts = content_import_conflict_facts(
            imported_article_id=imported_article_id,
            title=title,
        )
    except ImportContentError as exc:
        raise ImportDecisionError(exc.code, "导入文章信息无效。") from None
    return ImportConflictFacts(facts.id_owner_id, facts.exact_title_owner_ids)


def resolve_import_metadata(
    *, section_name: object, tag_names: object
) -> ImportMetadataMapping:
    try:
        mapping = content_resolve_import_metadata(
            section_name=section_name,
            tag_names=tag_names,
        )
    except ImportContentError as exc:
        raise ImportDecisionError(exc.code, "导入元数据无法映射。") from None
    return ImportMetadataMapping(
        mapping.section_id,
        mapping.tag_ids,
        mapping.proposed_tag_names,
    )


def validate_import_mapping(
    *, section_id, tag_ids: object, proposed_tag_names: object
) -> ImportMetadataMapping:
    try:
        mapping = content_validate_import_mapping(
            section_id=section_id,
            tag_ids=tag_ids,
            proposed_tag_names=proposed_tag_names,
        )
    except ImportContentError as exc:
        raise ImportDecisionError(exc.code, "导入元数据选择无效。") from None
    return ImportMetadataMapping(
        mapping.section_id,
        mapping.tag_ids,
        mapping.proposed_tag_names,
    )


def create_configured_import_preview(
    *,
    actor_id,
    source_name: str,
    source_kind: str,
    chunks: Iterable[bytes],
):
    limits = ImportLimits(
        compressed_bytes=settings.EXCHANGE_IMPORT_COMPRESSED_MAX_BYTES,
        expanded_bytes=settings.EXCHANGE_IMPORT_EXPANDED_MAX_BYTES,
        item_count=settings.EXCHANGE_IMPORT_ITEM_MAX_COUNT,
        path_depth=settings.EXCHANGE_IMPORT_PATH_MAX_DEPTH,
        compression_ratio=settings.EXCHANGE_IMPORT_COMPRESSION_MAX_RATIO,
        body_bytes=settings.ARTICLE_BODY_MAX_BYTES,
    )
    created = create_import_preview(
        actor_id=actor_id,
        source_name=source_name,
        source_kind=source_kind,
        chunks=chunks,
        staging=ImportStaging(settings.EXCHANGE_IMPORT_ROOT),
        author_check=active_import_author,
        markdown_renderer=render_import_markdown,
        image_validator=validate_import_image,
        limits=limits,
    )
    classified = classify_import_preview(
        actor_id=actor_id,
        job_id=created.job_id,
        conflict_facts=import_conflict_facts,
        metadata_resolver=resolve_import_metadata,
    )
    return ImportPreviewResult(
        job_id=created.job_id,
        status=classified.status,
        item_count=len(classified.items),
        valid_count=int(classified.preview_summary["valid"]),
        invalid_count=int(classified.preview_summary["invalid"]),
        preview_version=classified.preview_version,
    )


def configured_import_preview(*, actor_id, job_id: str):
    return import_preview(actor_id=actor_id, job_id=job_id)


def update_configured_import_decision(
    *,
    actor_id,
    job_id: str,
    item_id: str,
    expected_preview_version: int,
    included: bool,
    decision: str,
    section_id,
    tag_ids: object,
    proposed_tag_names: object,
    trace_code: str,
    client_ip: str,
):
    return update_import_decision(
        actor_id=actor_id,
        job_id=job_id,
        item_id=item_id,
        expected_preview_version=expected_preview_version,
        included=included,
        decision=decision,
        section_id=section_id,
        tag_ids=tag_ids,
        proposed_tag_names=proposed_tag_names,
        trace_code=trace_code,
        client_ip=client_ip,
        author_check=active_import_author,
        mapping_validator=validate_import_mapping,
        audit_writer=record_audit_entry,
    )


def _dispatch_import_job(job_id: str, preview_version: int) -> None:
    from apps.exchange.tasks.import_job import process_import_job_task

    process_import_job_task.delay(job_id, preview_version)


def confirm_configured_import(
    *,
    actor_id,
    job_id: str,
    expected_preview_version: int,
    trace_code: str,
    client_ip: str,
):
    return confirm_import(
        actor_id=actor_id,
        job_id=job_id,
        expected_preview_version=expected_preview_version,
        trace_code=trace_code,
        client_ip=client_ip,
        author_check=active_import_author,
        audit_writer=record_audit_entry,
        dispatcher=_dispatch_import_job,
    )


def imported_content_result(*, actor_id, import_key: str):
    try:
        result = content_imported_article_result(
            actor_id=actor_id,
            import_key=import_key,
        )
    except ImportArticleError as exc:
        from apps.exchange.public import ImportProcessingError

        raise ImportProcessingError(exc.code, exc.safe_message) from None
    if result is None:
        return None
    return ImportContentResult(
        result.article_id,
        result.revision_id,
        result.publication_status,
    )


def write_import_content(*, actor_id, command: ImportContentCommand, trace_code: str):
    try:
        result = write_content_import_item(
            actor_id=actor_id,
            command=ContentImportArticleCommand(
                import_key=command.import_key,
                operation=command.operation,
                article_id=command.article_id,
                title=command.title,
                body_markdown=command.body_markdown,
                visibility=command.visibility,
                summary_mode=command.summary_mode,
                custom_summary=command.custom_summary,
                section_id=command.section_id,
                tag_ids=command.tag_ids,
                proposed_tag_names=command.proposed_tag_names,
                cover_asset_id=command.cover_asset_id,
                body_asset_ids=command.body_asset_ids,
                comments_enabled=command.comments_enabled,
                comments_view_login=command.comments_view_login,
                comments_post_login=command.comments_post_login,
                publication_status=command.publication_status,
                scheduled_for=command.scheduled_for,
                published_at=command.published_at,
            ),
            trace_code=trace_code,
        )
    except ImportArticleError as exc:
        from apps.exchange.public import ImportProcessingError

        raise ImportProcessingError(exc.code, exc.safe_message) from None
    return ImportContentResult(
        result.article_id,
        result.revision_id,
        result.publication_status,
    )


def create_import_media(
    *, owner_id, article_id: str, purpose: str, original_name: str, content: bytes
):
    asset = create_media_import_asset(
        owner_id=owner_id,
        article_id=article_id,
        purpose=MediaPurpose(purpose),
        original_name=original_name,
        content=content,
        storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
        capacity_check=partial(require_image_creation_capacity, settings.MEDIA_ROOT),
    )
    return ImportMediaResult(asset.asset_id, asset.purpose)


def cleanup_import_media(*, owner_id, asset_ids: tuple[str, ...]):
    return discard_media_import_assets(
        owner_id=owner_id,
        asset_ids=asset_ids,
        storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
    )


def process_configured_import_job(
    job_id: str,
    preview_version: int,
    *,
    trace_code: str | None = None,
):
    return process_import_job(
        job_id=job_id,
        preview_version=preview_version,
        staging=ImportStaging(settings.EXCHANGE_IMPORT_ROOT),
        content_writer=write_import_content,
        existing_result=imported_content_result,
        media_creator=create_import_media,
        media_cleanup=cleanup_import_media,
        warning_recipient=active_administrator_id,
        trace_code=trace_code or new_trace_code(),
    )


def configured_export_storage() -> ExportArchiveStorage:
    return ExportArchiveStorage(settings.EXCHANGE_EXPORT_ROOT)


def _dispatch_export_job(job_id: str) -> None:
    from apps.exchange.tasks.export_job import build_export_task

    build_export_task.delay(job_id)


def request_configured_export(
    *,
    actor_id,
    scope: str,
    scope_author_id=None,
    scope_section_id=None,
    article_ids=(),
    trace_code: str,
    client_ip: str,
):
    return request_export(
        actor_id=actor_id,
        scope=scope,
        scope_author_id=scope_author_id,
        scope_section_id=scope_section_id,
        article_ids=article_ids,
        trace_code=trace_code,
        client_ip=client_ip,
        administrator_check=is_administrator,
        selection_provider=export_article_snapshots,
        audit_writer=record_audit_entry,
        dispatcher=_dispatch_export_job,
    )


def build_configured_export(job_id: str, *, heartbeat=lambda: None):
    media_storage = FilesystemMediaStorage(settings.MEDIA_ROOT)
    return build_export_archive(
        job_id=job_id,
        storage=configured_export_storage(),
        revision_provider=export_revision_payloads,
        media_index_provider=export_revision_media,
        media_reader=lambda *, asset_id: read_export_media(
            asset_id=asset_id,
            storage=media_storage,
        ),
        heartbeat=heartbeat,
    )


def cancel_configured_export(
    *,
    actor_id,
    job_id: str,
    trace_code: str,
    client_ip: str,
):
    return cancel_export(
        actor_id=actor_id,
        job_id=job_id,
        trace_code=trace_code,
        client_ip=client_ip,
        storage=configured_export_storage(),
        administrator_check=is_administrator,
        audit_writer=record_audit_entry,
    )


def configured_export_download(
    *,
    actor_id,
    job_id: str,
    trace_code: str,
    client_ip: str,
):
    return export_download(
        actor_id=actor_id,
        job_id=job_id,
        trace_code=trace_code,
        client_ip=client_ip,
        storage=configured_export_storage(),
        administrator_check=is_administrator,
        audit_writer=record_audit_entry,
    )


def open_configured_export_archive(grant):
    return open_export_archive(grant, storage=configured_export_storage())


def configured_due_export_expiry_ids() -> tuple[str, ...]:
    return due_export_expiry_ids(batch_size=settings.EXCHANGE_EXPORT_EXPIRY_BATCH_SIZE)


def expire_configured_export(job_id: str):
    return expire_export(job_id=job_id, storage=configured_export_storage())


def mark_configured_export_final_failed(*, job_id: str, error_code: str):
    return mark_export_task_final_failed(
        job_id=job_id,
        error_code=error_code,
        storage=configured_export_storage(),
    )
