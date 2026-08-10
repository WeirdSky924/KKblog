import json
import stat
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from apps.core.ids import normalize_ulid

_LOSSY_HEADER = (
    "<!-- Lossy convenience copy generated from TipTap JSON. "
    "Source of truth: body.tiptap.json. -->\n\n"
)


class ExportArchiveFormatError(ValueError):
    pass


def _json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _json_bytes(value) -> bytes:
    return (
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


class _Writer:
    def __init__(self, stream, *, generated_at: datetime) -> None:
        self.archive = ZipFile(
            stream,
            mode="w",
            compression=ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        )
        moment = generated_at.astimezone(UTC)
        self.timestamp = (
            max(1980, moment.year),
            moment.month,
            moment.day,
            moment.hour,
            moment.minute,
            moment.second,
        )
        self.names: set[str] = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.archive.close()

    def write(self, name: str, content: bytes) -> None:
        path = PurePosixPath(name)
        if (
            not isinstance(name, str)
            or not name
            or "\\" in name
            or path.is_absolute()
            or ".." in path.parts
            or name in self.names
        ):
            raise ExportArchiveFormatError("Invalid export archive entry")
        if not isinstance(content, bytes):
            raise TypeError("Export archive content must be bytes")
        info = ZipInfo(name, self.timestamp)
        info.compress_type = ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o600) << 16
        info.create_system = 3
        self.archive.writestr(info, content)
        self.names.add(name)

    def write_json(self, name: str, value) -> None:
        self.write(name, _json_bytes(value))


def _revision_metadata(revision, media_items) -> dict[str, object]:
    return {
        "article_id": revision.article_id,
        "based_on_id": revision.based_on_id,
        "comments": {
            "enabled": revision.comments_enabled,
            "post_login_required": revision.comments_post_login,
            "view_login_required": revision.comments_view_login,
        },
        "content_format": revision.content_format,
        "tiptap_schema_version": revision.tiptap_schema_version,
        "cover_asset_id": revision.cover_asset_id,
        "attachment_asset_id": revision.attachment_asset_id,
        "created_at": revision.created_at,
        "created_by_id": revision.created_by_id,
        "custom_summary": revision.custom_summary,
        "media": media_items,
        "reason": revision.reason,
        "restore_source_id": revision.restore_source_id,
        "revision_id": revision.revision_id,
        "section": {
            "id": revision.section_id,
            "name": revision.section_name,
        },
        "sequence": revision.sequence,
        "summary_mode": revision.summary_mode,
        "tags": [
            {"id": tag.tag_id, "name": tag.name, "state": tag.state}
            for tag in revision.tags
        ],
        "title": revision.title,
        "visibility": revision.visibility,
    }


def _selection_metadata(selection, revision_entries) -> dict[str, object]:
    return {
        "article_id": selection.article_id,
        "author_id": selection.author_id,
        "deleted_at": selection.deleted_at,
        "publication_state": selection.publication_state,
        "published_at": selection.published_at,
        "published_revision_id": selection.published_revision_id,
        "purge_after": selection.purge_after,
        "revision_ids": list(selection.revision_ids),
        "revisions": revision_entries,
        "scheduled_for": selection.scheduled_for,
        "scheduled_revision_id": selection.scheduled_revision_id,
        "section_id": selection.section_id,
        "visibility": selection.visibility,
        "working_revision_id": selection.working_revision_id,
    }


def write_export_zip(
    stream,
    *,
    job_id: str,
    generated_at: datetime,
    selections,
    revision_provider,
    media_index_provider,
    media_reader,
    progress,
) -> dict[str, int]:
    identity = normalize_ulid(job_id)
    if generated_at.tzinfo is None:
        raise ExportArchiveFormatError("Export timestamp must be timezone-aware")
    if not all(
        callable(port)
        for port in (revision_provider, media_index_provider, media_reader, progress)
    ):
        raise TypeError("Export archive ports are required")
    manifest_articles = []
    manifest_assets: dict[str, dict[str, object]] = {}
    revision_count = 0
    with _Writer(stream, generated_at=generated_at) as writer:
        for selection in selections:
            progress()
            revision_ids = tuple(selection.revision_ids)
            revisions = tuple(revision_provider(revision_ids=revision_ids))
            by_id = {revision.revision_id: revision for revision in revisions}
            if set(by_id) != set(revision_ids) or len(by_id) != len(revision_ids):
                raise ExportArchiveFormatError("Export revision payload is incomplete")
            media_by_revision = media_index_provider(revision_ids=revision_ids)
            if set(media_by_revision) != set(revision_ids):
                raise ExportArchiveFormatError("Export media index is incomplete")
            revision_entries = []
            for revision_id in revision_ids:
                progress()
                revision = by_id[revision_id]
                if revision.article_id != selection.article_id:
                    raise ExportArchiveFormatError(
                        "Export revision belongs to another article"
                    )
                prefix = (
                    f"articles/{selection.article_id}/revisions/"
                    f"{revision.sequence:06d}-{revision.revision_id}"
                )
                media_items = []
                for media in media_by_revision[revision_id]:
                    asset_path = f"media/{media.asset_id}.{media.extension}"
                    descriptor = {
                        "asset_id": media.asset_id,
                        "detected_mime": media.detected_mime,
                        "path": asset_path,
                        "purpose": media.purpose,
                        "sha256": media.sha256,
                        "size_bytes": media.size_bytes,
                    }
                    existing = manifest_assets.get(media.asset_id)
                    if existing is not None and existing != descriptor:
                        raise ExportArchiveFormatError(
                            "Export media descriptor changed within archive"
                        )
                    if existing is None:
                        content = media_reader(asset_id=media.asset_id)
                        if (
                            len(content) != media.size_bytes
                            or sha256(content).hexdigest() != media.sha256
                        ):
                            raise ExportArchiveFormatError(
                                "Export media content failed verification"
                            )
                        writer.write(asset_path, content)
                        manifest_assets[media.asset_id] = descriptor
                    media_items.append({**descriptor, "slot": media.slot})
                    progress()
                metadata_path = f"{prefix}/metadata.json"
                writer.write_json(
                    metadata_path,
                    _revision_metadata(revision, media_items),
                )
                if revision.content_format == "MARKDOWN":
                    if (
                        revision.body_markdown is None
                        or revision.body_tiptap is not None
                        or revision.tiptap_schema_version is not None
                    ):
                        raise ExportArchiveFormatError(
                            "Invalid Markdown export payload"
                        )
                    writer.write(
                        f"{prefix}/body.md", revision.body_markdown.encode("utf-8")
                    )
                    markdown_role = "source"
                elif revision.content_format == "TIPTAP_JSON":
                    if (
                        revision.body_tiptap is None
                        or revision.body_markdown is not None
                        or revision.tiptap_schema_version not in {1, 2}
                    ):
                        raise ExportArchiveFormatError("Invalid TipTap export payload")
                    writer.write_json(
                        f"{prefix}/body.tiptap.json", revision.body_tiptap
                    )
                    writer.write(
                        f"{prefix}/body.md",
                        (_LOSSY_HEADER + revision.convenience_markdown).encode("utf-8"),
                    )
                    markdown_role = "lossy_convenience"
                else:
                    raise ExportArchiveFormatError("Unsupported export content format")
                revision_entries.append(
                    {
                        "content_format": revision.content_format,
                        "markdown_role": markdown_role,
                        "metadata_path": metadata_path,
                        "revision_id": revision.revision_id,
                        "sequence": revision.sequence,
                    }
                )
                revision_count += 1
            article_metadata = _selection_metadata(selection, revision_entries)
            article_path = f"articles/{selection.article_id}/article.json"
            writer.write_json(article_path, article_metadata)
            manifest_articles.append(
                {
                    "article_id": selection.article_id,
                    "article_path": article_path,
                    "author_id": selection.author_id,
                    "revision_count": len(revision_entries),
                }
            )
        writer.write_json(
            "manifest.json",
            {
                "articles": manifest_articles,
                "format": "kaj-content-export",
                "generated_at": generated_at,
                "job_id": identity,
                "media": list(manifest_assets.values()),
                "tiptap_markdown_is_lossy": True,
                "version": 1,
            },
        )
    return {
        "article_count": len(manifest_articles),
        "media_count": len(manifest_assets),
        "revision_count": revision_count,
    }
