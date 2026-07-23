from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_active_author
from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    MediaTargetType,
    bind_revision_snapshot_assets,
    target_binding_snapshot,
)

from ..events import ARTICLE_VISIBILITY_CHANGED
from ..models import Article, ArticleRevision, RevisionTag, Tag
from ..snapshots import Visibility
from .articles import ContentCommandError
from .publication import _render_for_publication


@dataclass(frozen=True, slots=True)
class VisibilityChangeResult:
    article_id: str
    revision_id: str
    visibility: str
    body_markdown: str | None
    published_at: datetime
    last_published_at: datetime


def _actor(value) -> UUID:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.article_not_editable.v1", "文章不存在或不可编辑。"
        ) from None
    if not is_active_author(actor):
        raise ContentCommandError(
            "content.article_not_editable.v1", "文章不存在或不可编辑。"
        )
    return actor


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.article_not_editable.v1", "文章不存在或不可编辑。"
        ) from None


def _result(
    article: Article, revision: ArticleRevision, now: datetime
) -> VisibilityChangeResult:
    assert article.published_at is not None
    return VisibilityChangeResult(
        article.id,
        revision.id,
        revision.visibility,
        revision.body_markdown,
        article.published_at,
        now,
    )


def change_visibility(
    *,
    actor_id,
    article_id: str,
    visibility: Visibility | str,
    trace_code: str,
    clock: Clock | None = None,
) -> VisibilityChangeResult:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    try:
        desired = Visibility(visibility)
    except (TypeError, ValueError):
        raise ContentCommandError(
            "content.visibility_invalid.v1", "文章可见性不合法。"
        ) from None
    active_clock = clock or SystemClock()
    now = active_clock.now()
    try:
        with transaction.atomic():
            try:
                article = Article.objects.select_for_update().get(
                    pk=identity,
                    author_id=actor,
                    deleted_at__isnull=True,
                    published_revision__isnull=False,
                )
            except Article.DoesNotExist:
                raise ContentCommandError(
                    "content.article_not_editable.v1", "文章不存在或不可编辑。"
                ) from None
            source = ArticleRevision.objects.get(pk=article.published_revision_id)
            if source.visibility == desired:
                return _result(article, source, article.last_published_at or now)
            sequence = (
                article.revisions.order_by("-sequence")
                .values_list("sequence", flat=True)
                .first()
                + 1
            )
            revision = ArticleRevision.objects.create(
                article=article,
                sequence=sequence,
                based_on=source,
                created_by_id=actor,
                content_format=source.content_format,
                title=source.title,
                body_markdown=source.body_markdown,
                body_tiptap=source.body_tiptap,
                summary_mode=source.summary_mode,
                custom_summary=source.custom_summary,
                visibility=desired,
                section_id=source.section_id,
                cover_asset_id=source.cover_asset_id,
                comments_enabled=source.comments_enabled,
                comments_view_login=source.comments_view_login,
                comments_post_login=source.comments_post_login,
            )
            tags = tuple(
                row.tag
                for row in source.tag_snapshots.select_related("tag")
                if row.tag.state in {Tag.State.PENDING, Tag.State.ACTIVE}
            )
            RevisionTag.objects.bulk_create(
                [RevisionTag(revision=revision, tag=tag) for tag in tags]
            )
            bindings = target_binding_snapshot(
                target_type=MediaTargetType.ARTICLE_REVISION,
                target_id=source.id,
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
            previous = source.visibility
            article.published_revision = revision
            if article.publication_state != Article.PublicationState.SCHEDULED:
                article.publication_state = Article.PublicationState.PUBLISHED
            article.last_published_at = now
            article.save(
                update_fields=(
                    "published_revision",
                    "publication_state",
                    "last_published_at",
                    "updated_at",
                )
            )
            enqueue_event(
                ARTICLE_VISIBILITY_CHANGED,
                aggregate_type="article",
                aggregate_id=article.id,
                actor_id=actor,
                trace_code=trace_code,
                payload={
                    "revision_id": revision.id,
                    "from": previous,
                    "to": desired,
                },
                clock=active_clock,
            )
    except MediaBindingError:
        raise ContentCommandError(
            "content.media_invalid.v1", "文章图片当前不可用。"
        ) from None
    return _result(article, revision, now)
