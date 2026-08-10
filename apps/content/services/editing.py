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
from apps.media.public import MediaPurpose, MediaTargetType, target_binding_snapshot

from ..models import Article, ArticleEditGrant, ArticleRevision, Tag
from ..policies import article_is_reader_masked
from ..snapshots import ArticleSnapshot, ArticleWriteResult
from .articles import ContentCommandError, save_revision

EDIT_TOKEN_LIFETIME = timedelta(hours=12)


class EditTokenError(ValueError):
    code = "content.edit_token_invalid.v1"

    def __init__(self) -> None:
        super().__init__("编辑会话已失效，请重新打开文章。")


@dataclass(frozen=True, slots=True)
class RevisionMetadata:
    revision_id: str
    sequence: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EditConflict:
    article_id: str
    baseline: RevisionMetadata
    current: RevisionMetadata


@dataclass(frozen=True, slots=True)
class EditSession:
    grant_id: str
    article_id: str
    baseline_revision_id: str
    row_version: int
    token: str
    expires_at: datetime
    snapshot: ArticleSnapshot


class EditConflictError(RuntimeError):
    code = "content.edit_conflict.v1"

    def __init__(self, conflict: EditConflict, session: EditSession) -> None:
        self.conflict = conflict
        self.session = session
        super().__init__("文章已在其他会话中保存，请选择编辑基线。")


@dataclass(frozen=True, slots=True)
class EditSaveResult:
    write: ArticleWriteResult
    next_session: EditSession


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _actor(value) -> UUID:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        raise EditTokenError from None
    if not is_active_author(actor):
        raise EditTokenError
    return actor


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise EditTokenError from None


def _metadata(revision: ArticleRevision) -> RevisionMetadata:
    return RevisionMetadata(revision.id, revision.sequence, revision.created_at)


def _snapshot(revision: ArticleRevision) -> ArticleSnapshot:
    bindings = target_binding_snapshot(
        target_type=MediaTargetType.ARTICLE_REVISION,
        target_id=revision.id,
    )
    body_ids = tuple(
        binding.asset_id for binding in bindings if binding.purpose == MediaPurpose.BODY
    )
    attachment_ids = tuple(
        binding.asset_id
        for binding in bindings
        if binding.purpose == MediaPurpose.ATTACHMENT
    )
    tag_ids = tuple(
        row.tag_id
        for row in revision.tag_snapshots.select_related("tag")
        if row.tag.state in {Tag.State.PENDING, Tag.State.ACTIVE}
    )
    body = (
        revision.body_markdown
        if revision.content_format == ArticleRevision.ContentFormat.MARKDOWN
        else revision.body_tiptap
    )
    assert body is not None
    return ArticleSnapshot(
        content_format=revision.content_format,
        title=revision.title,
        body=body,
        tiptap_schema_version=revision.tiptap_schema_version,
        summary_mode=revision.summary_mode,
        custom_summary=revision.custom_summary,
        visibility=revision.visibility,
        section_id=revision.section_id,
        tag_ids=tag_ids,
        cover_asset_id=revision.cover_asset_id,
        attachment_asset_id=(attachment_ids[0] if attachment_ids else None),
        body_asset_ids=body_ids,
        comments_enabled=revision.comments_enabled,
        comments_view_login=revision.comments_view_login,
        comments_post_login=revision.comments_post_login,
    )


def _issue_grant(
    *,
    article: Article,
    revision: ArticleRevision,
    actor_id: UUID,
    clock: Clock,
    state: str = ArticleEditGrant.State.ACTIVE,
) -> EditSession:
    now = clock.now()
    grant = ArticleEditGrant(
        article=article,
        baseline_revision=revision,
        actor_id=actor_id,
        row_version=article.row_version,
        state=state,
        expires_at=now + EDIT_TOKEN_LIFETIME,
    )
    secret = secrets.token_urlsafe(32)
    token = f"{grant.id}.{secret}"
    grant.token_digest = _digest(token)
    grant.save(force_insert=True)
    return EditSession(
        grant.id,
        article.id,
        revision.id,
        article.row_version,
        token,
        grant.expires_at,
        _snapshot(revision),
    )


def _locked_grant(token: str) -> ArticleEditGrant:
    if not isinstance(token, str) or token.count(".") != 1:
        raise EditTokenError
    grant_id, secret = token.split(".", 1)
    if not secret:
        raise EditTokenError
    try:
        grant = ArticleEditGrant.objects.select_for_update().get(
            pk=normalize_ulid(grant_id)
        )
    except (TypeError, ValueError, ArticleEditGrant.DoesNotExist):
        raise EditTokenError from None
    if not secrets.compare_digest(grant.token_digest, _digest(token)):
        raise EditTokenError
    return grant


def open_edit_session(
    *, actor_id, article_id: str, clock: Clock | None = None
) -> EditSession:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    active_clock = clock or SystemClock()
    conflict_error: EditConflictError | None = None
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(
                pk=identity,
                author_id=actor,
                deleted_at__isnull=True,
                working_revision__isnull=False,
            )
        except Article.DoesNotExist:
            raise EditTokenError from None
        if article_is_reader_masked(article.id):
            raise EditTokenError
        conflict_grant = (
            article.edit_grants.select_related("baseline_revision")
            .filter(
                actor_id=actor,
                state=ArticleEditGrant.State.CONFLICT,
            )
            .order_by("-updated_at", "-id")
            .first()
        )
        current = ArticleRevision.objects.get(pk=article.working_revision_id)
        if conflict_grant is not None:
            baseline = conflict_grant.baseline_revision
            ArticleEditGrant.objects.filter(
                article=article,
                state=ArticleEditGrant.State.CONFLICT,
            ).update(state=ArticleEditGrant.State.REPLACED)
            session = _issue_grant(
                article=article,
                revision=baseline,
                actor_id=actor,
                clock=active_clock,
                state=ArticleEditGrant.State.CONFLICT,
            )
            conflict_error = EditConflictError(
                EditConflict(
                    article.id,
                    _metadata(baseline),
                    _metadata(current),
                ),
                session,
            )
        elif article.edit_grants.filter(state=ArticleEditGrant.State.CONFLICT).exists():
            raise EditTokenError
        else:
            session = _issue_grant(
                article=article,
                revision=current,
                actor_id=actor,
                clock=active_clock,
            )
    if conflict_error is not None:
        raise conflict_error
    return session


def save_revision_with_token(
    *,
    actor_id,
    article_id: str,
    edit_token: str,
    snapshot: ArticleSnapshot,
    capacity_check=None,
    clock: Clock | None = None,
) -> EditSaveResult:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    active_clock = clock or SystemClock()
    now = active_clock.now()
    conflict_error: EditConflictError | None = None
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(
                pk=identity,
                author_id=actor,
                deleted_at__isnull=True,
                working_revision__isnull=False,
            )
        except Article.DoesNotExist:
            raise EditTokenError from None
        if article_is_reader_masked(article.id):
            raise EditTokenError
        grant = _locked_grant(edit_token)
        if (
            grant.actor_id != actor
            or grant.article_id != article.id
            or grant.state != ArticleEditGrant.State.ACTIVE
            or grant.expires_at <= now
        ):
            raise EditTokenError
        baseline = ArticleRevision.objects.get(pk=grant.baseline_revision_id)
        current = ArticleRevision.objects.get(pk=article.working_revision_id)
        if grant.row_version != article.row_version:
            grant.state = ArticleEditGrant.State.CONFLICT
            grant.save(update_fields=("state", "updated_at"))
            conflict = EditConflict(
                article.id,
                _metadata(baseline),
                _metadata(current),
            )
            conflict_session = EditSession(
                grant.id,
                article.id,
                baseline.id,
                grant.row_version,
                edit_token,
                grant.expires_at,
                _snapshot(baseline),
            )
            conflict_error = EditConflictError(conflict, conflict_session)
        else:
            try:
                write = save_revision(
                    actor_id=actor,
                    article_id=article.id,
                    expected_row_version=article.row_version,
                    snapshot=snapshot,
                    base_revision_id=baseline.id,
                    capacity_check=capacity_check,
                )
            except ContentCommandError:
                raise
            grant.state = ArticleEditGrant.State.CONSUMED
            grant.save(update_fields=("state", "updated_at"))
            new_revision = ArticleRevision.objects.get(pk=write.revision_id)
            article.refresh_from_db(fields=("row_version", "working_revision"))
            next_session = _issue_grant(
                article=article,
                revision=new_revision,
                actor_id=actor,
                clock=active_clock,
            )
    if conflict_error is not None:
        raise conflict_error
    return EditSaveResult(write, next_session)


def resolve_edit_conflict(
    *,
    actor_id,
    article_id: str,
    conflict_token: str,
    selected_revision_id: str,
    clock: Clock | None = None,
) -> EditSession:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    try:
        selected_id = normalize_ulid(selected_revision_id)
    except (TypeError, ValueError):
        raise EditTokenError from None
    active_clock = clock or SystemClock()
    now = active_clock.now()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(
                pk=identity,
                author_id=actor,
                deleted_at__isnull=True,
            )
        except Article.DoesNotExist:
            raise EditTokenError from None
        if article_is_reader_masked(article.id):
            raise EditTokenError
        grant = _locked_grant(conflict_token)
        if (
            grant.actor_id != actor
            or grant.article_id != article.id
            or grant.state != ArticleEditGrant.State.CONFLICT
            or grant.expires_at <= now
        ):
            raise EditTokenError
        try:
            selected = ArticleRevision.objects.get(pk=selected_id, article=article)
        except ArticleRevision.DoesNotExist:
            raise EditTokenError from None
        ArticleEditGrant.objects.filter(
            article=article,
            state=ArticleEditGrant.State.CONFLICT,
        ).update(state=ArticleEditGrant.State.REPLACED)
        return _issue_grant(
            article=article,
            revision=selected,
            actor_id=actor,
            clock=active_clock,
        )
