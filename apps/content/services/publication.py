from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_active_author
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.media.public import (
    MediaBindingError,
    MediaPurpose,
    MediaTargetType,
    RenderingError,
    markdown_media_ids,
    render_markdown,
    render_tiptap,
    target_binding_snapshot,
    tiptap_media_ids,
)

from ..events import ARTICLE_PUBLISHED
from ..models import Article, ArticleRevision, PublicationReviewGrant, Tag
from ..policies import article_is_reader_masked, author_is_content_masked
from ..rendering_policy import configured_content_embed_policy

REVIEW_LIFETIME = timedelta(minutes=15)


class PublicationCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PublicationReview:
    grant_id: str
    revision_id: str
    row_version: int
    token: str
    expires_at: datetime
    title: str
    sanitized_html: str
    content_format: str
    summary_mode: str
    custom_summary: str | None
    visibility: str
    section_name: str
    tag_names: tuple[str, ...]
    cover_asset_id: str | None
    comments_enabled: bool
    comments_view_login: bool
    comments_post_login: bool
    first_publication: bool


@dataclass(frozen=True, slots=True)
class PublicationResult:
    article_id: str
    revision_id: str
    first: bool
    published_at: datetime
    last_published_at: datetime


@dataclass(frozen=True, slots=True)
class PreferenceRepublishResult:
    published: bool
    article_id: str
    revision_id: str


def _actor(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise PublicationCommandError(
            "content.article_not_editable.v1", "文章不存在或不可发布。"
        ) from None
    if not is_active_author(actor_id) or author_is_content_masked(actor_id):
        raise PublicationCommandError(
            "content.article_not_editable.v1", "文章不存在或不可发布。"
        )
    return actor_id


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise PublicationCommandError(
            "content.article_not_editable.v1", "文章不存在或不可发布。"
        ) from None


def _revision_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise PublicationCommandError(
            "content.revision_not_publishable.v1", "修订不存在或不可发布。"
        ) from None


def _row_version(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PublicationCommandError(
            "content.edit_conflict.v1", "文章版本已发生变化。"
        )
    return value


def _load_target(
    *,
    actor_id: UUID,
    article_id: str,
    revision_id: str,
    expected_row_version: int,
) -> tuple[Article, ArticleRevision]:
    try:
        article = Article.objects.select_for_update().get(
            pk=article_id,
            deleted_at__isnull=True,
        )
    except Article.DoesNotExist:
        raise PublicationCommandError(
            "content.article_not_editable.v1", "文章不存在或不可发布。"
        ) from None
    if article.author_id != actor_id:
        raise PublicationCommandError(
            "content.article_not_editable.v1", "文章不存在或不可发布。"
        )
    if article_is_reader_masked(article.id):
        raise PublicationCommandError(
            "content.article_not_editable.v1", "文章不存在或不可发布。"
        )
    if article.row_version != expected_row_version:
        raise PublicationCommandError(
            "content.edit_conflict.v1", "文章版本已发生变化。"
        )
    try:
        revision = ArticleRevision.objects.get(pk=revision_id, article=article)
    except ArticleRevision.DoesNotExist:
        raise PublicationCommandError(
            "content.revision_not_publishable.v1", "修订不存在或不可发布。"
        ) from None
    if article.working_revision_id != revision.id:
        raise PublicationCommandError(
            "content.revision_not_publishable.v1", "修订不是当前工作版本。"
        )
    return article, revision


def _render_for_publication(revision: ArticleRevision) -> str:
    try:
        bindings = target_binding_snapshot(
            target_type=MediaTargetType.ARTICLE_REVISION,
            target_id=revision.id,
        )
    except MediaBindingError:
        raise PublicationCommandError(
            "content.media_invalid.v1", "文章图片当前不可用。"
        ) from None
    if any(binding.state != "ACTIVE" for binding in bindings):
        raise PublicationCommandError(
            "content.media_invalid.v1", "文章图片当前不可用。"
        )
    body_ids = {
        binding.asset_id for binding in bindings if binding.purpose == MediaPurpose.BODY
    }
    cover_ids = {
        binding.asset_id
        for binding in bindings
        if binding.purpose == MediaPurpose.COVER
    }
    if revision.cover_asset_id is not None and cover_ids != {revision.cover_asset_id}:
        raise PublicationCommandError(
            "content.media_invalid.v1", "文章封面当前不可用。"
        )
    if revision.cover_asset_id is None and cover_ids:
        raise PublicationCommandError(
            "content.media_invalid.v1", "文章封面信息不一致。"
        )
    try:
        if revision.content_format == ArticleRevision.ContentFormat.MARKDOWN:
            referenced = set(markdown_media_ids(revision.body_markdown or ""))
            rendered = render_markdown(
                revision.body_markdown or "",
                embed_policy=configured_content_embed_policy(),
                allowed_media_ids=body_ids,
            )
        else:
            referenced = set(tiptap_media_ids(revision.body_tiptap or {}))
            rendered = render_tiptap(
                revision.body_tiptap or {},
                embed_policy=configured_content_embed_policy(),
                allowed_media_ids=body_ids,
            )
    except RenderingError:
        raise PublicationCommandError(
            "content.body_invalid.v1", "文章正文当前无法安全渲染。"
        ) from None
    if referenced != body_ids:
        raise PublicationCommandError(
            "content.media_invalid.v1", "正文图片绑定与正文不一致。"
        )
    return rendered.html


def _validate_publication(article: Article, revision: ArticleRevision) -> str:
    if article.edit_grants.filter(state="CONFLICT").exists():
        raise PublicationCommandError(
            "content.edit_conflict_unresolved.v1",
            "请先解决编辑冲突后再发布。",
        )
    if revision.section_id is None:
        raise PublicationCommandError(
            "content.section_required.v1", "发布文章前必须选择一个分区。"
        )
    revision_tags = tuple(revision.tag_snapshots.select_related("tag").all())
    if len(revision_tags) > 10 or any(
        item.tag.state in {Tag.State.REJECTED, Tag.State.DELETED}
        for item in revision_tags
    ):
        raise PublicationCommandError(
            "content.tag_invalid.v1", "文章标签当前不可发布。"
        )
    return _render_for_publication(revision)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def prepare_publication(
    *,
    actor_id,
    article_id: str,
    revision_id: str,
    expected_row_version: int,
    clock: Clock | None = None,
) -> PublicationReview:
    actor = _actor(actor_id)
    article_key = _article_id(article_id)
    revision_key = _revision_id(revision_id)
    version = _row_version(expected_row_version)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        article, revision = _load_target(
            actor_id=actor,
            article_id=article_key,
            revision_id=revision_key,
            expected_row_version=version,
        )
        sanitized_html = _validate_publication(article, revision)
        grant = PublicationReviewGrant(
            article=article,
            revision=revision,
            actor_id=actor,
            row_version=article.row_version,
            expires_at=now + REVIEW_LIFETIME,
            created_at=now,
        )
        secret = secrets.token_urlsafe(32)
        token = f"{grant.id}.{secret}"
        grant.token_digest = _digest(token)
        grant.save(force_insert=True)
    return PublicationReview(
        grant_id=grant.id,
        revision_id=revision.id,
        row_version=article.row_version,
        token=token,
        expires_at=grant.expires_at,
        title=revision.title,
        sanitized_html=sanitized_html,
        content_format=revision.content_format,
        summary_mode=revision.summary_mode,
        custom_summary=revision.custom_summary,
        visibility=revision.visibility,
        section_name=revision.section.name if revision.section_id else "未知分区",
        tag_names=tuple(
            row.tag.name
            for row in revision.tag_snapshots.select_related("tag").order_by("tag_id")
        ),
        cover_asset_id=revision.cover_asset_id,
        comments_enabled=revision.comments_enabled,
        comments_view_login=revision.comments_view_login,
        comments_post_login=revision.comments_post_login,
        first_publication=article.published_revision_id is None,
    )


def _locked_grant(token: str) -> PublicationReviewGrant:
    if not isinstance(token, str) or token.count(".") != 1:
        raise PublicationCommandError(
            "content.review_token_invalid.v1", "终稿审查已失效，请重新审查。"
        )
    grant_id, secret = token.split(".", 1)
    if not secret:
        raise PublicationCommandError(
            "content.review_token_invalid.v1", "终稿审查已失效，请重新审查。"
        )
    try:
        grant_id = normalize_ulid(grant_id)
        grant = PublicationReviewGrant.objects.select_for_update().get(pk=grant_id)
    except (TypeError, ValueError, PublicationReviewGrant.DoesNotExist):
        raise PublicationCommandError(
            "content.review_token_invalid.v1", "终稿审查已失效，请重新审查。"
        ) from None
    if not secrets.compare_digest(grant.token_digest, _digest(token)):
        raise PublicationCommandError(
            "content.review_token_invalid.v1", "终稿审查已失效，请重新审查。"
        )
    return grant


def _apply_publication(
    *,
    article: Article,
    revision: ArticleRevision,
    actor_id: UUID,
    trace_code: str,
    now: datetime,
    clock: Clock,
) -> PublicationResult:
    first = article.published_revision_id is None
    article.published_revision = revision
    article.publication_state = Article.PublicationState.PUBLISHED
    article.scheduled_revision = None
    article.scheduled_for = None
    article.scheduled_at = None
    if first:
        article.published_at = now
    article.last_published_at = now
    article.save(
        update_fields=(
            "published_revision",
            "publication_state",
            "scheduled_revision",
            "scheduled_for",
            "scheduled_at",
            "published_at",
            "last_published_at",
            "updated_at",
        )
    )
    enqueue_event(
        ARTICLE_PUBLISHED,
        aggregate_type="article",
        aggregate_id=article.id,
        actor_id=actor_id,
        trace_code=trace_code,
        payload={"revision_id": revision.id, "first": first},
        clock=clock,
    )
    assert article.published_at is not None
    return PublicationResult(
        article.id,
        revision.id,
        first,
        article.published_at,
        now,
    )


def publish_article(
    *,
    actor_id,
    article_id: str,
    revision_id: str,
    expected_row_version: int,
    review_token: str,
    trace_code: str,
    clock: Clock | None = None,
) -> PublicationResult:
    actor = _actor(actor_id)
    article_key = _article_id(article_id)
    revision_key = _revision_id(revision_id)
    version = _row_version(expected_row_version)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        article, revision = _load_target(
            actor_id=actor,
            article_id=article_key,
            revision_id=revision_key,
            expected_row_version=version,
        )
        grant = _locked_grant(review_token)
        if (
            grant.consumed_at is not None
            or grant.expires_at <= now
            or grant.actor_id != actor
            or grant.article_id != article.id
            or grant.revision_id != revision.id
            or grant.row_version != article.row_version
        ):
            raise PublicationCommandError(
                "content.review_token_invalid.v1", "终稿审查已失效，请重新审查。"
            )
        _validate_publication(article, revision)
        result = _apply_publication(
            article=article,
            revision=revision,
            actor_id=actor,
            trace_code=trace_code,
            now=now,
            clock=active_clock,
        )
        PublicationReviewGrant.objects.filter(
            article=article,
            revision=revision,
            row_version=article.row_version,
            consumed_at__isnull=True,
        ).update(consumed_at=now)
    return result


def republish_saved_revision(
    *,
    actor_id,
    article_id: str,
    revision_id: str,
    expected_row_version: int,
    auto_republish_enabled: bool,
    trace_code: str,
    clock: Clock | None = None,
) -> PreferenceRepublishResult:
    if type(auto_republish_enabled) is not bool:
        raise TypeError("auto_republish_enabled must be a boolean")
    article_key = _article_id(article_id)
    revision_key = _revision_id(revision_id)
    if not auto_republish_enabled:
        return PreferenceRepublishResult(False, article_key, revision_key)
    actor = _actor(actor_id)
    version = _row_version(expected_row_version)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        article, revision = _load_target(
            actor_id=actor,
            article_id=article_key,
            revision_id=revision_key,
            expected_row_version=version,
        )
        if article.published_revision_id is None or _restore_requires_review(
            article=article,
            revision=revision,
        ):
            raise PublicationCommandError(
                "content.final_review_required.v1", "该修订必须先完成终稿审查。"
            )
        _validate_publication(article, revision)
        _apply_publication(
            article=article,
            revision=revision,
            actor_id=actor,
            trace_code=trace_code,
            now=now,
            clock=active_clock,
        )
    return PreferenceRepublishResult(True, article.id, revision.id)


def _restore_requires_review(*, article: Article, revision: ArticleRevision) -> bool:
    current = revision
    visited: set[str] = set()
    for _ in range(1000):
        if current.id == article.published_revision_id:
            return False
        if current.id in visited or current.restore_source_id is not None:
            return True
        visited.add(current.id)
        if current.based_on_id is None:
            return False
        try:
            current = ArticleRevision.objects.only(
                "id", "article_id", "based_on_id", "restore_source_id"
            ).get(pk=current.based_on_id, article=article)
        except ArticleRevision.DoesNotExist:
            return True
    return True
