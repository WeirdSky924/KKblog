from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.db import transaction

from apps.accounts.public import is_active_author
from apps.core.ids import normalize_ulid
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    RenderingError,
    bind_revision_snapshot_assets,
    markdown_media_ids,
    render_markdown,
    render_tiptap,
    tiptap_media_ids,
)
from apps.operations.public import require_text_creation_capacity

from ..models import Article, ArticleRevision, ArticleTag, RevisionTag, Section, Tag
from ..policies import article_is_reader_masked
from ..snapshots import (
    ArticleBodyLimit,
    ArticleSnapshot,
    ArticleWriteResult,
    ContentFormat,
    SummaryMode,
    Visibility,
)

CapacityCheck = Callable[[], object]


class ContentCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _ValidatedSnapshot:
    content_format: str
    title: str
    body_markdown: str | None
    body_tiptap: dict | None
    summary_mode: str
    custom_summary: str | None
    visibility: str
    section_id: UUID | None
    tag_ids: tuple[UUID, ...]
    cover_asset_id: str | None
    body_asset_ids: tuple[str, ...]
    comments_enabled: bool
    comments_view_login: bool
    comments_post_login: bool


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.author_required.v1", "只有启用的作者可以编辑文章。"
        ) from None


def _require_author(actor_id: UUID) -> None:
    if not is_active_author(actor_id):
        raise ContentCommandError(
            "content.author_required.v1", "只有启用的作者可以编辑文章。"
        )


def _run_capacity_check(check: CapacityCheck | None) -> None:
    if check is None:
        require_text_creation_capacity(settings.BASE_DIR)
        return
    if not callable(check):
        raise TypeError("capacity_check must be callable")
    check()


def _normalize_media_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.media_invalid.v1", "正文或封面图片信息不合法。"
        ) from None


def _normalize_section_id(value) -> UUID | None:
    if value is None:
        return None
    try:
        section_id = UUID(str(value))
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.section_invalid.v1", "所选分区不存在。"
        ) from None
    if not Section.objects.filter(pk=section_id).exists():
        raise ContentCommandError("content.section_invalid.v1", "所选分区不存在。")
    return section_id


def _normalize_tag_ids(values) -> tuple[UUID, ...]:
    try:
        tag_ids = tuple(UUID(str(value)) for value in values)
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.tag_invalid.v1", "标签信息不合法。"
        ) from None
    if len(tag_ids) > 10 or len(set(tag_ids)) != len(tag_ids):
        raise ContentCommandError(
            "content.tag_invalid.v1", "每篇文章最多选择 10 个不重复标签。"
        )
    return tag_ids


def _validate_snapshot(
    snapshot: ArticleSnapshot,
    body_limit: ArticleBodyLimit | None,
) -> _ValidatedSnapshot:
    if not isinstance(snapshot, ArticleSnapshot):
        raise TypeError("snapshot must be an ArticleSnapshot")
    policy = body_limit or ArticleBodyLimit.configured()
    if not isinstance(policy, ArticleBodyLimit):
        raise TypeError("body_limit must be an ArticleBodyLimit")
    try:
        content_format = ContentFormat(snapshot.content_format)
        summary_mode = SummaryMode(snapshot.summary_mode)
        visibility = Visibility(snapshot.visibility)
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.snapshot_invalid.v1", "文章设置不合法。"
        ) from None
    if not isinstance(snapshot.title, str):
        raise ContentCommandError("content.title_invalid.v1", "标题不能为空。")
    title = snapshot.title.strip()
    if not title or len(title) > 30:
        raise ContentCommandError(
            "content.title_invalid.v1", "标题须为 1 至 30 个字符。"
        )

    custom_summary = snapshot.custom_summary
    if summary_mode == SummaryMode.CUSTOM:
        if not isinstance(custom_summary, str):
            raise ContentCommandError(
                "content.summary_invalid.v1", "自定义摘要不能为空。"
            )
        custom_summary = custom_summary.strip()
        if not custom_summary or len(custom_summary) > 100:
            raise ContentCommandError(
                "content.summary_invalid.v1", "自定义摘要须为 1 至 100 个字符。"
            )
    elif custom_summary is not None:
        raise ContentCommandError(
            "content.summary_invalid.v1", "当前摘要模式不能保存自定义摘要。"
        )

    if any(
        type(value) is not bool
        for value in (
            snapshot.comments_enabled,
            snapshot.comments_view_login,
            snapshot.comments_post_login,
        )
    ):
        raise ContentCommandError("content.snapshot_invalid.v1", "评论设置不合法。")
    try:
        body_ids = tuple(
            _normalize_media_id(value) for value in snapshot.body_asset_ids
        )
    except TypeError:
        raise ContentCommandError(
            "content.media_invalid.v1", "正文图片信息不合法。"
        ) from None
    if len(body_ids) > 1000 or len(set(body_ids)) != len(body_ids):
        raise ContentCommandError("content.media_invalid.v1", "正文图片信息不合法。")
    cover_id = _normalize_media_id(snapshot.cover_asset_id)
    section_id = _normalize_section_id(snapshot.section_id)
    tag_ids = _normalize_tag_ids(snapshot.tag_ids)

    try:
        if content_format == ContentFormat.MARKDOWN:
            if not isinstance(snapshot.body, str):
                raise RenderingError("Markdown source must be text")
            serialized = snapshot.body
            markdown, tiptap = snapshot.body, None
        else:
            if not isinstance(snapshot.body, dict):
                raise RenderingError("TipTap source must be an object")
            serialized = json.dumps(
                snapshot.body,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            markdown, tiptap = None, snapshot.body
    except (RenderingError, TypeError, ValueError, RecursionError):
        raise ContentCommandError(
            "content.body_invalid.v1", "正文格式不合法。"
        ) from None
    if len(serialized.encode("utf-8")) > policy.maximum_bytes:
        raise ContentCommandError(
            "content.body_too_large.v1",
            f"正文不能超过 {policy.maximum_bytes} 字节。",
        )
    try:
        if content_format == ContentFormat.MARKDOWN:
            referenced = markdown_media_ids(snapshot.body)
            render_markdown(snapshot.body, allowed_media_ids=set(body_ids))
        else:
            referenced = tiptap_media_ids(snapshot.body)
            render_tiptap(snapshot.body, allowed_media_ids=set(body_ids))
    except (RenderingError, TypeError, ValueError, RecursionError):
        raise ContentCommandError(
            "content.body_invalid.v1", "正文格式不合法。"
        ) from None
    if set(referenced) != set(body_ids):
        raise ContentCommandError(
            "content.media_invalid.v1", "正文图片引用与提交列表不一致。"
        )
    return _ValidatedSnapshot(
        content_format=content_format,
        title=title,
        body_markdown=markdown,
        body_tiptap=tiptap,
        summary_mode=summary_mode,
        custom_summary=custom_summary,
        visibility=visibility,
        section_id=section_id,
        tag_ids=tag_ids,
        cover_asset_id=cover_id,
        body_asset_ids=body_ids,
        comments_enabled=snapshot.comments_enabled,
        comments_view_login=snapshot.comments_view_login,
        comments_post_login=snapshot.comments_post_login,
    )


def _create_revision(
    *,
    article: Article,
    actor_id: UUID,
    sequence: int,
    snapshot: _ValidatedSnapshot,
    based_on: ArticleRevision | None = None,
) -> ArticleRevision:
    return ArticleRevision.objects.create(
        article=article,
        sequence=sequence,
        based_on=based_on,
        created_by_id=actor_id,
        content_format=snapshot.content_format,
        title=snapshot.title,
        body_markdown=snapshot.body_markdown,
        body_tiptap=snapshot.body_tiptap,
        summary_mode=snapshot.summary_mode,
        custom_summary=snapshot.custom_summary,
        visibility=snapshot.visibility,
        section_id=snapshot.section_id,
        cover_asset_id=snapshot.cover_asset_id,
        comments_enabled=snapshot.comments_enabled,
        comments_view_login=snapshot.comments_view_login,
        comments_post_login=snapshot.comments_post_login,
    )


def _lock_snapshot_tags(
    *, actor_id: UUID, tag_ids: tuple[UUID, ...]
) -> tuple[Tag, ...]:
    if not tag_ids:
        return ()
    tags = tuple(Tag.objects.select_for_update().filter(pk__in=tag_ids).order_by("id"))
    if len(tags) != len(tag_ids):
        raise ContentCommandError("content.tag_invalid.v1", "标签不存在或不可用。")
    by_id = {tag.id: tag for tag in tags}
    ordered = tuple(by_id[tag_id] for tag_id in tag_ids)
    if any(
        tag.state == Tag.State.REJECTED or tag.state == Tag.State.DELETED
        for tag in ordered
    ):
        raise ContentCommandError("content.tag_invalid.v1", "标签不存在或不可用。")
    return ordered


def _write_tag_snapshot(
    *, article: Article, revision: ArticleRevision, tags: tuple[Tag, ...]
) -> None:
    RevisionTag.objects.bulk_create(
        [RevisionTag(revision=revision, tag=tag) for tag in tags]
    )
    ArticleTag.objects.filter(article=article).exclude(
        tag_id__in=[tag.id for tag in tags]
    ).delete()
    existing = set(
        ArticleTag.objects.filter(article=article).values_list("tag_id", flat=True)
    )
    ArticleTag.objects.bulk_create(
        [ArticleTag(article=article, tag=tag) for tag in tags if tag.id not in existing]
    )


def _bind_media(
    *, actor_id: UUID, revision: ArticleRevision, snapshot: _ValidatedSnapshot
) -> None:
    inputs: list[BindingInput] = []
    if snapshot.cover_asset_id:
        inputs.append(BindingInput(snapshot.cover_asset_id, "cover"))
    inputs.extend(
        BindingInput(asset_id, f"body-{asset_id}")
        for asset_id in snapshot.body_asset_ids
    )
    if inputs:
        bind_revision_snapshot_assets(
            actor_id=actor_id,
            target_id=revision.id,
            inputs=tuple(inputs),
        )


def create_article(
    *,
    actor_id,
    snapshot: ArticleSnapshot,
    body_limit: ArticleBodyLimit | None = None,
    capacity_check: CapacityCheck | None = None,
) -> ArticleWriteResult:
    actor = _actor_id(actor_id)
    _require_author(actor)
    _run_capacity_check(capacity_check)
    validated = _validate_snapshot(snapshot, body_limit)
    try:
        with transaction.atomic():
            article = Article.objects.create(author_id=actor, row_version=1)
            tags = _lock_snapshot_tags(
                actor_id=actor,
                tag_ids=validated.tag_ids,
            )
            revision = _create_revision(
                article=article,
                actor_id=actor,
                sequence=1,
                snapshot=validated,
            )
            _write_tag_snapshot(article=article, revision=revision, tags=tags)
            _bind_media(actor_id=actor, revision=revision, snapshot=validated)
            article.working_revision = revision
            article.save(update_fields=("working_revision", "updated_at"))
    except MediaBindingError:
        raise ContentCommandError(
            "content.media_invalid.v1", "正文或封面图片不可用于这篇文章。"
        ) from None
    return ArticleWriteResult(article.id, revision.id, article.row_version)


def save_revision(
    *,
    actor_id,
    article_id: str,
    expected_row_version: int,
    snapshot: ArticleSnapshot,
    base_revision_id: str | None = None,
    body_limit: ArticleBodyLimit | None = None,
    capacity_check: CapacityCheck | None = None,
) -> ArticleWriteResult:
    actor = _actor_id(actor_id)
    _require_author(actor)
    _run_capacity_check(capacity_check)
    try:
        normalized_article_id = normalize_ulid(article_id)
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.article_not_editable.v1", "文章不存在或不可编辑。"
        ) from None
    if (
        isinstance(expected_row_version, bool)
        or not isinstance(expected_row_version, int)
        or expected_row_version < 1
    ):
        raise ContentCommandError("content.edit_conflict.v1", "文章版本已发生变化。")
    validated = _validate_snapshot(snapshot, body_limit)
    try:
        with transaction.atomic():
            try:
                article = Article.objects.select_for_update().get(
                    pk=normalized_article_id,
                    deleted_at__isnull=True,
                )
            except Article.DoesNotExist:
                raise ContentCommandError(
                    "content.article_not_editable.v1", "文章不存在或不可编辑。"
                ) from None
            if article.author_id != actor:
                raise ContentCommandError(
                    "content.article_not_editable.v1", "文章不存在或不可编辑。"
                )
            if article_is_reader_masked(article.id):
                raise ContentCommandError(
                    "content.article_not_editable.v1", "文章不存在或不可编辑。"
                )
            if article.edit_grants.filter(state="CONFLICT").exists():
                raise ContentCommandError(
                    "content.edit_conflict_unresolved.v1",
                    "请先解决编辑冲突后再继续。",
                )
            if article.row_version != expected_row_version:
                raise ContentCommandError(
                    "content.edit_conflict.v1", "文章版本已发生变化。"
                )
            working = article.working_revision
            if working is None:
                raise ContentCommandError(
                    "content.article_not_editable.v1", "文章不存在或不可编辑。"
                )
            based_on = working
            if base_revision_id is not None:
                try:
                    normalized_base = normalize_ulid(base_revision_id)
                    based_on = ArticleRevision.objects.get(
                        pk=normalized_base,
                        article=article,
                    )
                except (TypeError, ValueError, ArticleRevision.DoesNotExist):
                    raise ContentCommandError(
                        "content.revision_not_editable.v1",
                        "编辑基线不存在或不可用。",
                    ) from None
            if based_on.content_format != validated.content_format:
                raise ContentCommandError(
                    "content.format_immutable.v1", "文章格式不能在普通编辑中切换。"
                )
            tags = _lock_snapshot_tags(
                actor_id=actor,
                tag_ids=validated.tag_ids,
            )
            sequence = (
                article.revisions.order_by("-sequence")
                .values_list("sequence", flat=True)
                .first()
                + 1
            )
            revision = _create_revision(
                article=article,
                actor_id=actor,
                sequence=sequence,
                snapshot=validated,
                based_on=based_on,
            )
            _write_tag_snapshot(article=article, revision=revision, tags=tags)
            _bind_media(actor_id=actor, revision=revision, snapshot=validated)
            article.working_revision = revision
            article.row_version += 1
            article.save(
                update_fields=("working_revision", "row_version", "updated_at")
            )
    except MediaBindingError:
        raise ContentCommandError(
            "content.media_invalid.v1", "正文或封面图片不可用于这篇文章。"
        ) from None
    return ArticleWriteResult(article.id, revision.id, article.row_version)
