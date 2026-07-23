from __future__ import annotations

from dataclasses import dataclass
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

from ..events import ARTICLE_ADMIN_VIEWED
from ..models import AdminArticleViewReceipt, Article, ArticleRevision
from ..policies import article_is_reader_masked, author_is_content_masked


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
    visibility: str
    publication_state: str
    deleted_at: datetime | None
    can_edit: bool
    can_publish: bool
    admin_read_only: bool


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
) -> ArticleView:
    return ArticleView(
        article.id,
        revision.id,
        article.author_id,
        revision.title,
        revision.content_format,
        revision.body_markdown,
        revision.body_tiptap,
        revision.visibility,
        article.publication_state,
        article.deleted_at,
        can_edit,
        can_edit,
        admin_read_only,
    )


def article_for_reader(*, actor_id, article_id: str) -> ArticleView:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=False)
    try:
        article = Article.objects.select_related("published_revision").get(
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
    authenticated = actor is not None and is_active_account(actor)
    if revision.visibility == ArticleRevision.Visibility.PUBLIC:
        allowed = True
    elif revision.visibility == ArticleRevision.Visibility.AUTHENTICATED:
        if not authenticated:
            raise ArticleLoginRequired(article.id)
        allowed = True
    else:
        allowed = actor == article.author_id and is_active_author(actor)
    if not allowed:
        raise ArticleNotFound
    owner = actor == article.author_id and is_active_author(actor)
    return _view(article, revision, can_edit=owner, admin_read_only=False)


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
    return _view(
        article,
        article.working_revision,
        can_edit=article.deleted_at is None,
        admin_read_only=False,
    )


def article_for_admin(
    *,
    actor_id,
    article_id: str,
    revision: str,
    trace_code: str,
    clock: Clock | None = None,
) -> ArticleView:
    identity = _article_id(article_id)
    actor = _actor_id(actor_id, required=True)
    if not is_administrator(actor) or revision not in {"working", "published"}:
        raise ArticleNotFound
    active_clock = clock or SystemClock()
    with transaction.atomic():
        try:
            article = Article.objects.select_for_update().get(pk=identity)
        except Article.DoesNotExist:
            raise ArticleNotFound from None
        revision_id = (
            article.working_revision_id
            if revision == "working"
            else article.published_revision_id
        )
        if revision_id is None:
            raise ArticleNotFound
        selected = ArticleRevision.objects.get(pk=revision_id, article=article)
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
    return _view(
        article,
        selected,
        can_edit=actor == article.author_id and article.deleted_at is None,
        admin_read_only=actor != article.author_id,
    )
