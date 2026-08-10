from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_active_author
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    MediaTargetType,
    bind_revision_snapshot_assets,
    target_binding_snapshot,
)

from ..models import (
    Article,
    ArticleRestoreGrant,
    ArticleRevision,
    ArticleTag,
    RevisionTag,
    Tag,
)
from ..policies import article_is_reader_masked
from ..snapshots import ArticleSnapshot, ArticleWriteResult
from .editing import _snapshot
from .publication import _render_for_publication

RESTORE_LIFETIME = timedelta(minutes=15)


class RestoreCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RestorePreview:
    grant_id: str
    token: str
    expires_at: datetime
    source_revision_id: str
    current_revision_id: str
    row_version: int
    changed_fields: tuple[str, ...]
    source: ArticleSnapshot
    current: ArticleSnapshot
    source_section_name: str
    current_section_name: str
    source_tag_names: tuple[str, ...]
    current_tag_names: tuple[str, ...]


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _actor(value) -> UUID:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        raise RestoreCommandError(
            "content.restore_not_allowed.v1", "文章不存在或不可恢复。"
        ) from None
    if not is_active_author(actor):
        raise RestoreCommandError(
            "content.restore_not_allowed.v1", "文章不存在或不可恢复。"
        )
    return actor


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise RestoreCommandError(
            "content.restore_not_allowed.v1", "文章不存在或不可恢复。"
        ) from None


def _revision_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise RestoreCommandError(
            "content.restore_source_invalid.v1", "历史版本不存在或不可恢复。"
        ) from None


def _changed_fields(
    source: ArticleSnapshot, current: ArticleSnapshot
) -> tuple[str, ...]:
    fields: list[str] = []
    comparisons = (
        ("title", source.title, current.title),
        (
            "body",
            (source.content_format, source.body),
            (current.content_format, current.body),
        ),
        ("cover", source.cover_asset_id, current.cover_asset_id),
        ("attachment", source.attachment_asset_id, current.attachment_asset_id),
        ("visibility", source.visibility, current.visibility),
        ("section", source.section_id, current.section_id),
        ("tags", source.tag_ids, current.tag_ids),
        (
            "summary",
            (source.summary_mode, source.custom_summary),
            (current.summary_mode, current.custom_summary),
        ),
        (
            "comments",
            (
                source.comments_enabled,
                source.comments_view_login,
                source.comments_post_login,
            ),
            (
                current.comments_enabled,
                current.comments_view_login,
                current.comments_post_login,
            ),
        ),
    )
    for name, source_value, current_value in comparisons:
        if source_value != current_value:
            fields.append(name)
    return tuple(fields)


def prepare_restore_revision(
    *,
    actor_id,
    article_id: str,
    source_revision_id: str,
    clock: Clock | None = None,
) -> RestorePreview:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    source_id = _revision_id(source_revision_id)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(
                pk=identity,
                author_id=actor,
                deleted_at__isnull=True,
                working_revision__isnull=False,
            )
            source_revision = ArticleRevision.objects.get(
                pk=source_id,
                article=article,
            )
            current_revision = ArticleRevision.objects.get(
                pk=article.working_revision_id
            )
        except (Article.DoesNotExist, ArticleRevision.DoesNotExist):
            raise RestoreCommandError(
                "content.restore_source_invalid.v1",
                "历史版本不存在或不可恢复。",
            ) from None
        if article_is_reader_masked(article.id):
            raise RestoreCommandError(
                "content.restore_not_allowed.v1", "文章不存在或不可恢复。"
            )
        if article.edit_grants.filter(state="CONFLICT").exists():
            raise RestoreCommandError(
                "content.edit_conflict_unresolved.v1",
                "请先解决编辑冲突。",
            )
        source_snapshot = _snapshot(source_revision)
        current_snapshot = _snapshot(current_revision)
        grant = ArticleRestoreGrant(
            article=article,
            source_revision=source_revision,
            actor_id=actor,
            row_version=article.row_version,
            expires_at=now + RESTORE_LIFETIME,
            created_at=now,
        )
        secret = secrets.token_urlsafe(32)
        token = f"{grant.id}.{secret}"
        grant.token_digest = _digest(token)
        grant.save(force_insert=True)
    return RestorePreview(
        grant_id=grant.id,
        token=token,
        expires_at=grant.expires_at,
        source_revision_id=source_revision.id,
        current_revision_id=current_revision.id,
        row_version=article.row_version,
        changed_fields=_changed_fields(source_snapshot, current_snapshot),
        source=source_snapshot,
        current=current_snapshot,
        source_section_name=(
            source_revision.section.name if source_revision.section_id else "未知分区"
        ),
        current_section_name=(
            current_revision.section.name if current_revision.section_id else "未知分区"
        ),
        source_tag_names=tuple(
            row.tag.name
            for row in source_revision.tag_snapshots.select_related("tag").order_by(
                "tag_id"
            )
        ),
        current_tag_names=tuple(
            row.tag.name
            for row in current_revision.tag_snapshots.select_related("tag").order_by(
                "tag_id"
            )
        ),
    )


def _locked_grant(token: str) -> ArticleRestoreGrant:
    if not isinstance(token, str) or token.count(".") != 1:
        raise RestoreCommandError(
            "content.restore_token_invalid.v1", "恢复审查已失效，请重新操作。"
        )
    grant_id, secret = token.split(".", 1)
    if not secret:
        raise RestoreCommandError(
            "content.restore_token_invalid.v1", "恢复审查已失效，请重新操作。"
        )
    try:
        grant = ArticleRestoreGrant.objects.select_for_update().get(
            pk=normalize_ulid(grant_id)
        )
    except (TypeError, ValueError, ArticleRestoreGrant.DoesNotExist):
        raise RestoreCommandError(
            "content.restore_token_invalid.v1", "恢复审查已失效，请重新操作。"
        ) from None
    if not secrets.compare_digest(grant.token_digest, _digest(token)):
        raise RestoreCommandError(
            "content.restore_token_invalid.v1", "恢复审查已失效，请重新操作。"
        )
    return grant


def restore_revision(
    *,
    actor_id,
    article_id: str,
    source_revision_id: str,
    expected_row_version: int,
    restore_token: str,
    clock: Clock | None = None,
) -> ArticleWriteResult:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    source_id = _revision_id(source_revision_id)
    if (
        isinstance(expected_row_version, bool)
        or not isinstance(expected_row_version, int)
        or expected_row_version < 1
    ):
        raise RestoreCommandError("content.edit_conflict.v1", "文章版本已发生变化。")
    active_clock = clock or SystemClock()
    now = active_clock.now()
    try:
        with transaction.atomic():
            try:
                article = Article.objects.select_for_update().get(
                    pk=identity,
                    author_id=actor,
                    deleted_at__isnull=True,
                    working_revision__isnull=False,
                )
                source = ArticleRevision.objects.get(pk=source_id, article=article)
                current = ArticleRevision.objects.get(pk=article.working_revision_id)
            except (Article.DoesNotExist, ArticleRevision.DoesNotExist):
                raise RestoreCommandError(
                    "content.restore_source_invalid.v1",
                    "历史版本不存在或不可恢复。",
                ) from None
            if article_is_reader_masked(article.id):
                raise RestoreCommandError(
                    "content.restore_not_allowed.v1", "文章不存在或不可恢复。"
                )
            grant = _locked_grant(restore_token)
            if (
                grant.consumed_at is not None
                or grant.expires_at <= now
                or grant.actor_id != actor
                or grant.article_id != article.id
                or grant.source_revision_id != source.id
            ):
                raise RestoreCommandError(
                    "content.restore_token_invalid.v1",
                    "恢复审查已失效，请重新操作。",
                )
            if (
                grant.row_version != article.row_version
                or expected_row_version != article.row_version
            ):
                raise RestoreCommandError(
                    "content.edit_conflict.v1", "文章版本已发生变化。"
                )
            if article.edit_grants.filter(state="CONFLICT").exists():
                raise RestoreCommandError(
                    "content.edit_conflict_unresolved.v1",
                    "请先解决编辑冲突。",
                )
            tag_rows = tuple(source.tag_snapshots.select_related("tag").all())
            if any(
                row.tag.state not in {Tag.State.PENDING, Tag.State.ACTIVE}
                for row in tag_rows
            ):
                raise RestoreCommandError(
                    "content.restore_tag_unavailable.v1",
                    "历史版本包含当前不可用的标签。",
                )
            bindings = target_binding_snapshot(
                target_type=MediaTargetType.ARTICLE_REVISION,
                target_id=source.id,
            )
            if any(binding.state != "ACTIVE" for binding in bindings):
                raise RestoreCommandError(
                    "content.restore_media_unavailable.v1",
                    "历史版本包含当前不可用的图片。",
                )
            sequence = (
                article.revisions.order_by("-sequence")
                .values_list("sequence", flat=True)
                .first()
                + 1
            )
            revision = ArticleRevision.objects.create(
                article=article,
                sequence=sequence,
                based_on=current,
                restore_source=source,
                created_by_id=actor,
                content_format=source.content_format,
                title=source.title,
                body_markdown=source.body_markdown,
                body_tiptap=source.body_tiptap,
                tiptap_schema_version=source.tiptap_schema_version,
                summary_mode=source.summary_mode,
                custom_summary=source.custom_summary,
                visibility=source.visibility,
                section_id=source.section_id,
                cover_asset_id=source.cover_asset_id,
                attachment_asset_id=source.attachment_asset_id,
                comments_enabled=source.comments_enabled,
                comments_view_login=source.comments_view_login,
                comments_post_login=source.comments_post_login,
            )
            tags = tuple(row.tag for row in tag_rows)
            RevisionTag.objects.bulk_create(
                [RevisionTag(revision=revision, tag=tag) for tag in tags]
            )
            ArticleTag.objects.filter(article=article).delete()
            ArticleTag.objects.bulk_create(
                [ArticleTag(article=article, tag=tag) for tag in tags]
            )
            if bindings:
                bind_revision_snapshot_assets(
                    actor_id=actor,
                    target_id=revision.id,
                    inputs=tuple(
                        BindingInput(binding.asset_id, binding.slot)
                        for binding in bindings
                    ),
                )
            _render_for_publication(revision)
            article.working_revision = revision
            article.row_version += 1
            article.save(
                update_fields=("working_revision", "row_version", "updated_at")
            )
            ArticleRestoreGrant.objects.filter(
                article=article,
                source_revision=source,
                row_version=grant.row_version,
                consumed_at__isnull=True,
            ).update(consumed_at=now)
    except MediaBindingError:
        raise RestoreCommandError(
            "content.restore_media_unavailable.v1",
            "历史版本包含当前不可用的图片。",
        ) from None
    return ArticleWriteResult(article.id, revision.id, article.row_version)
