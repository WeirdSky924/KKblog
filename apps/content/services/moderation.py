from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_administrator
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock

from ..models import Article, ArticleRevision, ArticleTombstone
from ..policies import article_administrative_action_allowed
from .deletion import restore_deleted_article


class ArticleModerationAction(StrEnum):
    HIDE = "HIDE"
    DELETE = "DELETE"


class ArticleModerationBoundaryError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class ArticleModerationTarget:
    article_id: str
    author_id: UUID
    publication_state: str
    working_revision_id: str | None
    published_revision_id: str | None
    scheduled_revision_id: str | None
    scheduled_for: datetime | None
    scheduled_at: datetime | None
    published_at: datetime | None
    last_published_at: datetime | None
    visibility: str | None
    row_version: int

    def safe_snapshot(self) -> dict[str, object]:
        return {
            "version": 1,
            "article_id": self.article_id,
            "author_id": str(self.author_id),
            "publication_state": self.publication_state,
            "working_revision_id": self.working_revision_id,
            "published_revision_id": self.published_revision_id,
            "scheduled_revision_id": self.scheduled_revision_id,
            "scheduled_for": _iso(self.scheduled_for),
            "scheduled_at": _iso(self.scheduled_at),
            "published_at": _iso(self.published_at),
            "last_published_at": _iso(self.last_published_at),
            "visibility": self.visibility,
            "row_version": self.row_version,
        }


@dataclass(frozen=True, slots=True)
class ArticleModerationRecoveryResult:
    article_id: str
    publication_state: str
    row_version: int
    changed: bool


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _actor(value) -> UUID:
    try:
        actor = UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleModerationBoundaryError(
            "content.article_moderation_not_allowed.v1",
            "文章不存在或不能执行该管理操作。",
        ) from None
    if not is_administrator(actor):
        raise ArticleModerationBoundaryError(
            "content.article_moderation_not_allowed.v1",
            "文章不存在或不能执行该管理操作。",
        )
    return actor


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleModerationBoundaryError(
            "content.article_moderation_not_allowed.v1",
            "文章不存在或不能执行该管理操作。",
        ) from None


def _action(value) -> ArticleModerationAction:
    try:
        return ArticleModerationAction(value)
    except (TypeError, ValueError):
        raise ArticleModerationBoundaryError(
            "content.article_moderation_action_invalid.v1",
            "文章管理动作无效。",
        ) from None


def _target(article: Article) -> ArticleModerationTarget:
    visibility = None
    if article.published_revision_id is not None:
        visibility = (
            ArticleRevision.objects.filter(
                pk=article.published_revision_id,
                article=article,
            )
            .values_list("visibility", flat=True)
            .first()
        )
        if visibility is None:
            raise ArticleModerationBoundaryError(
                "content.article_moderation_state_invalid.v1",
                "文章当前状态不完整，不能执行管理操作。",
            )
    return ArticleModerationTarget(
        article.id,
        article.author_id,
        article.publication_state,
        article.working_revision_id,
        article.published_revision_id,
        article.scheduled_revision_id,
        article.scheduled_for,
        article.scheduled_at,
        article.published_at,
        article.last_published_at,
        visibility,
        article.row_version,
    )


def prepare_article_moderation_action(
    *,
    actor_id,
    article_id: str,
    action: ArticleModerationAction | str,
) -> ArticleModerationTarget:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    normalized_action = _action(action)
    with transaction.atomic():
        article = Article.objects.select_for_update().filter(pk=identity).first()
        if (
            article is None
            or article.author_id == actor
            or article.deleted_at is not None
            or article.purge_after is not None
        ):
            raise ArticleModerationBoundaryError(
                "content.article_moderation_not_allowed.v1",
                "文章不存在或不能执行该管理操作。",
            )
        target = _target(article)
        if normalized_action == ArticleModerationAction.HIDE and (
            target.publication_state != Article.PublicationState.PUBLISHED
            or target.published_revision_id is None
        ):
            raise ArticleModerationBoundaryError(
                "content.article_hide_not_allowed.v1",
                "只有已发布文章可以隐藏。",
            )
        return target


def _snapshot_mapping(value) -> dict[str, object]:
    expected = {
        "version",
        "article_id",
        "author_id",
        "publication_state",
        "working_revision_id",
        "published_revision_id",
        "scheduled_revision_id",
        "scheduled_for",
        "scheduled_at",
        "published_at",
        "last_published_at",
        "visibility",
        "row_version",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ArticleModerationBoundaryError(
            "content.article_moderation_snapshot_invalid.v1",
            "文章恢复材料无效。",
        )
    normalized = dict(value)
    if (
        normalized["version"] != 1
        or isinstance(normalized["row_version"], bool)
        or not isinstance(normalized["row_version"], int)
        or normalized["row_version"] < 1
    ):
        raise ArticleModerationBoundaryError(
            "content.article_moderation_snapshot_invalid.v1",
            "文章恢复材料无效。",
        )
    return normalized


def _delete_snapshot_matches(
    article: Article,
    tombstone: ArticleTombstone,
    snapshot: dict[str, object],
) -> bool:
    expected = {
        "version": 1,
        "article_id": article.id,
        "author_id": str(article.author_id),
        "publication_state": tombstone.original_publication_state,
        "working_revision_id": tombstone.original_working_revision_id,
        "published_revision_id": tombstone.original_published_revision_id,
        "scheduled_revision_id": tombstone.original_scheduled_revision_id,
        "scheduled_for": _iso(tombstone.original_scheduled_for),
        "scheduled_at": _iso(tombstone.original_scheduled_at),
        "published_at": _iso(tombstone.original_published_at),
        "last_published_at": _iso(tombstone.original_last_published_at),
        "visibility": None,
        "row_version": snapshot["row_version"],
    }
    if tombstone.original_published_revision_id is not None:
        expected["visibility"] = (
            ArticleRevision.objects.filter(
                pk=tombstone.original_published_revision_id,
                article=article,
            )
            .values_list("visibility", flat=True)
            .first()
        )
    return (
        tombstone.administrative
        and article.row_version == snapshot["row_version"] + 1
        and expected == snapshot
    )


def restore_article_from_moderation(
    *,
    actor_id,
    case_id: str,
    article_id: str,
    action: ArticleModerationAction | str,
    pre_action_snapshot,
    trace_code: str,
    client_ip: str,
    clock: Clock | None = None,
) -> ArticleModerationRecoveryResult:
    actor = _actor(actor_id)
    identity = _article_id(article_id)
    normalized_action = _action(action)
    if not article_administrative_action_allowed(
        actor_id=actor,
        article_id=identity,
        case_id=case_id,
        action=normalized_action.value,
        operation="RESTORE",
    ):
        raise ArticleModerationBoundaryError(
            "content.article_moderation_not_allowed.v1",
            "文章不存在或不能执行该管理操作。",
        )
    snapshot = _snapshot_mapping(pre_action_snapshot)
    if snapshot["article_id"] != identity:
        raise ArticleModerationBoundaryError(
            "content.article_moderation_snapshot_invalid.v1",
            "文章恢复材料无效。",
        )
    with transaction.atomic():
        article = Article.objects.select_for_update().filter(pk=identity).first()
        if article is None or str(article.author_id) != snapshot["author_id"]:
            raise ArticleModerationBoundaryError(
                "content.article_moderation_target_missing.v1",
                "文章当前无法恢复。",
            )
        if normalized_action == ArticleModerationAction.HIDE:
            if _target(article).safe_snapshot() != snapshot:
                raise ArticleModerationBoundaryError(
                    "content.article_moderation_state_conflict.v1",
                    "文章状态已变化，当前无法恢复。",
                )
            return ArticleModerationRecoveryResult(
                article.id,
                article.publication_state,
                article.row_version,
                False,
            )
        tombstone = (
            ArticleTombstone.objects.select_for_update()
            .filter(
                article_id=identity,
                purged_at__isnull=True,
            )
            .first()
        )
        if tombstone is None or not _delete_snapshot_matches(
            article, tombstone, snapshot
        ):
            raise ArticleModerationBoundaryError(
                "content.article_moderation_state_conflict.v1",
                "文章状态已变化，当前无法恢复。",
            )
        restored = restore_deleted_article(
            actor_id=actor,
            article_id=identity,
            expected_row_version=article.row_version,
            trace_code=trace_code,
            client_ip=client_ip,
            moderation_case_id=case_id,
            clock=clock,
        )
        return ArticleModerationRecoveryResult(
            restored.article_id,
            restored.publication_state,
            restored.row_version,
            restored.changed,
        )
