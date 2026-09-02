from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Q

from apps.accounts.public import (
    is_active_account,
    is_active_author,
    is_administrator,
)
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.core.time.shanghai import shanghai_business_date
from apps.media.public import (
    MediaAccessError,
    MediaPurpose,
    MediaTargetType,
    TipTapAttachmentMetadata,
    TipTapOutlineItem,
    authorize_asset_read,
    project_tiptap_outline,
    target_binding_snapshot,
)

from ..events import ARTICLE_ADMIN_VIEWED
from ..models import AdminArticleViewReceipt, Article, ArticleRevision, RevisionTag, Tag
from ..policies import article_is_reader_masked, author_is_content_masked
from ..rendering import ArticleRenderingMode, render_article_body
from ..rendering_policy import (
    content_rendering_version,
)
from .classification import TagItem
from .covers import ArticleCoverCandidate, resolve_article_covers
from .publication_history import admin_published_revision_exists


class ArticleNotFound(LookupError):
    code = "content.not_found.v1"

    def __init__(self) -> None:
        super().__init__("未找到请求的文章。")


class ArticleLoginRequired(PermissionError):
    code = "content.login_required.v1"

    def __init__(self, article_id: str) -> None:
        self.article_id = article_id
        super().__init__("登录后可查看这篇文章。")


@dataclass(frozen=True, slots=True)
class ArticleView:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    content_format: str
    body_markdown: str | None
    body_tiptap: dict[str, Any] | None
    tiptap_schema_version: int | None
    visibility: str
    publication_state: str
    deleted_at: datetime | None
    cover_asset_id: str | None
    attachment_asset_id: str | None
    tags: tuple[TagItem, ...]
    published_at: datetime | None
    scheduled_for: datetime | None
    published_revision_id: str | None
    scheduled_revision_id: str | None
    can_edit: bool
    can_publish: bool
    admin_read_only: bool
    row_version: int
    can_discard_cloud_draft: bool
    has_unpublished_changes: bool
    rendered_body_html: str | None = None
    readable_cover_asset_id: str | None = None
    readable_attachment_asset_id: str | None = None
    outline: tuple[TipTapOutlineItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ArticleReaderTarget:
    article_id: str
    revision_id: str


@dataclass(frozen=True, slots=True)
class ArticleCommentTarget:
    article_id: str
    revision_id: str
    owner_id: UUID
    visibility: str
    comments_enabled: bool
    view_login_required: bool
    post_login_required: bool


@dataclass(frozen=True, slots=True)
class PublicArticleCacheSnapshot:
    article_id: str
    revision_id: str
    author_id: UUID
    title: str
    content_format: str
    visibility: str
    published_at: datetime
    readable_cover_asset_id: str | None
    readable_attachment_asset_id: str | None
    tags: tuple[TagItem, ...]
    sanitizer_version: str
    outline: tuple[TipTapOutlineItem, ...]


@dataclass(frozen=True, slots=True)
class PublicArticleRender:
    article_id: str
    revision_id: str
    html: str
    sanitizer_version: str


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleNotFound from None


def _actor_id(value, *, required: bool) -> UUID | None:
    if value is None and not required:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleNotFound from None


def _view(
    article: Article,
    revision: ArticleRevision,
    *,
    can_edit: bool,
    admin_read_only: bool,
    include_pending_tags: bool,
) -> ArticleView:
    latest_published_at = article.latest_published_at
    can_discard_cloud_draft = (
        can_edit
        and article.publication_state != Article.PublicationState.SCHEDULED
        and (
            article.published_revision_id is None
            or article.working_revision_id != article.published_revision_id
        )
    )
    return ArticleView(
        article_id=article.id,
        revision_id=revision.id,
        author_id=article.author_id,
        title=revision.title,
        content_format=revision.content_format,
        body_markdown=revision.body_markdown,
        body_tiptap=revision.body_tiptap,
        tiptap_schema_version=revision.tiptap_schema_version,
        visibility=revision.visibility,
        publication_state=article.publication_state,
        deleted_at=article.deleted_at,
        cover_asset_id=revision.cover_asset_id,
        attachment_asset_id=revision.attachment_asset_id,
        tags=_visible_revision_tags(
            revision,
            include_pending=include_pending_tags,
        ),
        published_at=latest_published_at,
        scheduled_for=article.scheduled_for,
        published_revision_id=article.published_revision_id,
        scheduled_revision_id=article.scheduled_revision_id,
        can_edit=can_edit,
        can_publish=can_edit,
        admin_read_only=admin_read_only,
        row_version=article.row_version,
        can_discard_cloud_draft=can_discard_cloud_draft,
        has_unpublished_changes=(
            article.published_revision_id is None
            or article.working_revision_id != article.published_revision_id
        ),
        outline=_revision_outline(revision),
    )


def _visible_revision_tags(
    revision: ArticleRevision, *, include_pending: bool
) -> tuple[TagItem, ...]:
    states = (
        (Tag.State.ACTIVE, Tag.State.PENDING)
        if include_pending
        else (Tag.State.ACTIVE,)
    )
    rows = (
        RevisionTag.objects.select_related("tag")
        .filter(revision=revision)
        .filter(tag__state__in=states)
        .order_by("tag__normalized_name", "tag_id")
    )
    return tuple(TagItem(row.tag_id, row.tag.name, row.tag.state) for row in rows)


def _revision_outline(revision: ArticleRevision) -> tuple[TipTapOutlineItem, ...]:
    if (
        revision.content_format != ArticleRevision.ContentFormat.TIPTAP_JSON
        or revision.body_tiptap is None
        or revision.tiptap_schema_version is None
    ):
        return ()
    return project_tiptap_outline(
        revision.body_tiptap,
        schema_version=revision.tiptap_schema_version,
    )


def _reader_article(
    identity: str, *, lightweight: bool = False
) -> tuple[Article, ArticleRevision]:
    query = Article.objects.select_related("published_revision")
    if lightweight:
        # Bookmark and reaction commands only need access fields. Avoid loading
        # the potentially large Markdown/TipTap body just to authorize a write.
        query = query.only(
            "id",
            "author_id",
            "deleted_at",
            "published_revision_id",
            "published_revision__id",
            "published_revision__visibility",
        )
    try:
        article = query.get(
            pk=identity,
            deleted_at__isnull=True,
            published_revision__isnull=False,
        )
    except Article.DoesNotExist:
        raise ArticleNotFound from None
    revision = article.published_revision
    if (
        revision is None
        or not is_active_account(article.author_id)
        or author_is_content_masked(article.author_id)
        or article_is_reader_masked(article.id)
    ):
        raise ArticleNotFound
    return article, revision


def _require_reader_access(
    article: Article, revision: ArticleRevision, actor: UUID | None
) -> None:
    if revision.visibility == ArticleRevision.Visibility.PUBLIC:
        return
    authenticated = actor is not None and is_active_account(actor)
    if revision.visibility == ArticleRevision.Visibility.AUTHENTICATED:
        if not authenticated:
            raise ArticleLoginRequired(article.id)
        return
    if actor != article.author_id or not is_active_author(actor):
        raise ArticleNotFound


def article_reader_target(*, actor_id, article_id: str) -> ArticleReaderTarget:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=False)
    article, revision = _reader_article(identity, lightweight=True)
    _require_reader_access(article, revision, actor)
    return ArticleReaderTarget(article_id=article.id, revision_id=revision.id)


def article_for_reader(*, actor_id, article_id: str) -> ArticleView:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=False)
    article, revision = _reader_article(identity)
    _require_reader_access(article, revision, actor)
    owner = actor == article.author_id and is_active_author(actor)
    rendered_body_html, readable_cover_asset_id, readable_attachment_asset_id = (
        _reader_media(revision, actor_id=actor)
    )
    return replace(
        _view(
            article,
            revision,
            can_edit=owner,
            admin_read_only=False,
            include_pending_tags=False,
        ),
        rendered_body_html=rendered_body_html,
        readable_cover_asset_id=readable_cover_asset_id,
        readable_attachment_asset_id=readable_attachment_asset_id,
    )


def article_comment_target(*, actor_id, article_id: str) -> ArticleCommentTarget:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=False)
    article, revision = _reader_article(identity)
    _require_reader_access(article, revision, actor)
    return ArticleCommentTarget(
        article_id=article.id,
        revision_id=revision.id,
        owner_id=article.author_id,
        visibility=revision.visibility,
        comments_enabled=revision.comments_enabled,
        view_login_required=revision.comments_view_login,
        post_login_required=revision.comments_post_login,
    )


def public_article_cache_snapshot(*, article_id: str) -> PublicArticleCacheSnapshot:
    identity = _article_id(article_id)
    article, revision = _reader_article(identity)
    if revision.visibility != ArticleRevision.Visibility.PUBLIC:
        raise ArticleNotFound
    _, readable_cover_asset_id, readable_attachment_asset_id = _reader_media_bindings(
        revision
    )
    latest_published_at = article.latest_published_at
    if latest_published_at is None:
        raise ArticleNotFound
    return PublicArticleCacheSnapshot(
        article_id=article.id,
        revision_id=revision.id,
        author_id=article.author_id,
        title=revision.title,
        content_format=revision.content_format,
        visibility=revision.visibility,
        published_at=latest_published_at,
        readable_cover_asset_id=readable_cover_asset_id,
        readable_attachment_asset_id=readable_attachment_asset_id,
        tags=_visible_revision_tags(revision, include_pending=False),
        sanitizer_version=content_rendering_version(),
        outline=_revision_outline(revision),
    )


def render_public_article_body(
    *, article_id: str, revision_id: str
) -> PublicArticleRender:
    identity = _article_id(article_id)
    try:
        expected_revision = normalize_ulid(revision_id)
    except (TypeError, ValueError):
        raise ArticleNotFound from None
    article, revision = _reader_article(identity)
    if (
        revision.visibility != ArticleRevision.Visibility.PUBLIC
        or revision.id != expected_revision
    ):
        raise ArticleNotFound
    rendered_body_html, _, _ = _reader_media(revision, actor_id=None)
    return PublicArticleRender(
        article_id=article.id,
        revision_id=revision.id,
        html=rendered_body_html,
        sanitizer_version=content_rendering_version(),
    )


def _reader_media_bindings(
    revision: ArticleRevision,
) -> tuple[set[str], str | None, str | None]:
    bindings = target_binding_snapshot(
        target_type=MediaTargetType.ARTICLE_REVISION,
        target_id=revision.id,
    )
    active_body_ids = {
        item.asset_id
        for item in bindings
        if item.purpose == MediaPurpose.BODY and item.state == "ACTIVE"
    }
    active_cover_ids = {
        item.asset_id
        for item in bindings
        if item.purpose == MediaPurpose.COVER and item.state == "ACTIVE"
    }
    readable_cover_asset_id = (
        revision.cover_asset_id if revision.cover_asset_id in active_cover_ids else None
    )
    readable_cover_asset_id = resolve_article_covers(
        (
            ArticleCoverCandidate(
                revision.id,
                readable_cover_asset_id,
                revision.section_id,
            ),
        )
    )[revision.id].asset_id
    active_attachment_ids = {
        item.asset_id
        for item in bindings
        if item.purpose == MediaPurpose.ATTACHMENT and item.state == "ACTIVE"
    }
    readable_attachment_asset_id = (
        revision.attachment_asset_id
        if revision.attachment_asset_id in active_attachment_ids
        else None
    )
    return active_body_ids, readable_cover_asset_id, readable_attachment_asset_id


def _reader_media(
    revision: ArticleRevision,
    *,
    actor_id: UUID | None,
) -> tuple[str, str | None, str | None]:
    active_body_ids, readable_cover_asset_id, readable_attachment_asset_id = (
        _reader_media_bindings(revision)
    )
    if revision.content_format == ArticleRevision.ContentFormat.MARKDOWN:
        body = revision.body_markdown or ""
        attachment_metadata = None
    else:
        body = revision.body_tiptap or {}
        attachment_metadata = None
        if readable_attachment_asset_id is not None:
            try:
                attachment = authorize_asset_read(
                    actor_id=actor_id,
                    asset_id=readable_attachment_asset_id,
                )
            except MediaAccessError:
                pass
            else:
                attachment_metadata = TipTapAttachmentMetadata(
                    asset_id=attachment.asset_id,
                    original_name=attachment.original_name,
                    detected_mime=attachment.detected_mime,
                    size_bytes=attachment.size_bytes,
                )
    rendered = render_article_body(
        content_format=revision.content_format,
        body=body,
        tiptap_schema_version=revision.tiptap_schema_version,
        allowed_media_ids=active_body_ids,
        allowed_attachment_id=readable_attachment_asset_id,
        attachment_metadata=attachment_metadata,
        mode=ArticleRenderingMode.READER,
    )
    return rendered.html, readable_cover_asset_id, readable_attachment_asset_id


def article_for_author(
    *,
    actor_id,
    article_id: str,
    clock: Clock | None = None,
) -> ArticleView:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=True)
    if not is_active_author(actor) or author_is_content_masked(actor):
        raise ArticleNotFound
    now = (clock or SystemClock()).now()
    try:
        article = Article.objects.select_related("working_revision").get(
            Q(deleted_at__isnull=True) | Q(purge_after__gt=now),
            pk=identity,
            author_id=actor,
            working_revision__isnull=False,
        )
    except Article.DoesNotExist:
        raise ArticleNotFound from None
    assert article.working_revision is not None
    moderated = article_is_reader_masked(article.id)
    return _view(
        article,
        article.working_revision,
        can_edit=article.deleted_at is None and not moderated,
        admin_read_only=False,
        include_pending_tags=True,
    )


def _article_revision_for_admin(
    *,
    actor_id,
    article_id: str,
    trace_code: str,
    revision: str | None = None,
    revision_id: str | None = None,
    clock: Clock | None = None,
) -> ArticleView:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=True)
    if not is_administrator(actor):
        raise ArticleNotFound
    if (revision is None) == (revision_id is None):
        raise ArticleNotFound
    if revision is not None and revision not in {"working", "published"}:
        raise ArticleNotFound
    if revision_id is not None:
        try:
            revision_id = normalize_ulid(revision_id)
        except (TypeError, ValueError):
            raise ArticleNotFound from None
    active_clock = clock or SystemClock()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(pk=identity)
        except Article.DoesNotExist:
            raise ArticleNotFound from None
        selected_revision_id = revision_id
        if revision is not None:
            selected_revision_id = (
                article.working_revision_id
                if revision == "working"
                else article.published_revision_id
            )
        elif not admin_published_revision_exists(
            article=article,
            revision_id=revision_id or "",
        ):
            raise ArticleNotFound
        if selected_revision_id is None:
            raise ArticleNotFound
        try:
            selected = ArticleRevision.objects.get(
                pk=selected_revision_id,
                article=article,
            )
        except ArticleRevision.DoesNotExist:
            raise ArticleNotFound from None
        if actor != article.author_id:
            day = shanghai_business_date(active_clock.now())
            _, created = AdminArticleViewReceipt.objects.get_or_create(
                administrator_id=actor,
                author_id=article.author_id,
                article=article,
                view_date=day,
            )
            if created:
                enqueue_event(
                    ARTICLE_ADMIN_VIEWED,
                    aggregate_type="article",
                    aggregate_id=article.id,
                    actor_id=actor,
                    trace_code=trace_code,
                    payload={
                        "recipient_id": str(article.author_id),
                        "view_date": day.isoformat(),
                    },
                    clock=active_clock,
                )
    rendered_body_html, readable_cover_asset_id, readable_attachment_asset_id = (
        _reader_media(selected, actor_id=actor)
    )
    return replace(
        _view(
            article,
            selected,
            can_edit=actor == article.author_id and article.deleted_at is None,
            admin_read_only=actor != article.author_id,
            include_pending_tags=True,
        ),
        rendered_body_html=rendered_body_html,
        readable_cover_asset_id=readable_cover_asset_id,
        readable_attachment_asset_id=readable_attachment_asset_id,
    )


def article_for_admin(
    *,
    actor_id,
    article_id: str,
    revision: str,
    trace_code: str,
    clock: Clock | None = None,
) -> ArticleView:
    return _article_revision_for_admin(
        actor_id=actor_id,
        article_id=article_id,
        revision=revision,
        trace_code=trace_code,
        clock=clock,
    )


def article_published_revision_for_admin(
    *,
    actor_id,
    article_id: str,
    revision_id: str,
    trace_code: str,
    clock: Clock | None = None,
) -> ArticleView:
    return _article_revision_for_admin(
        actor_id=actor_id,
        article_id=article_id,
        revision_id=revision_id,
        trace_code=trace_code,
        clock=clock,
    )
