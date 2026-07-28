from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.content.public import ArticleNotFound
from apps.core.ids import normalize_ulid

from ..models import DiscussionThread
from ..targets import DiscussionTargetType
from .threads import sync_article_thread


class ArticleCommentSettingsError(LookupError):
    def __init__(self, message: str = "文章评论设置当前不可修改。") -> None:
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ArticleCommentSettingsResult:
    article_id: str
    comments_enabled: bool
    changed: bool


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ArticleCommentSettingsError from None


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ArticleCommentSettingsError from None


def set_article_comments_enabled(
    *, actor_id, article_id: str, enabled: bool
) -> ArticleCommentSettingsResult:
    actor = _actor_id(actor_id)
    identity = _article_id(article_id)
    if type(enabled) is not bool:
        raise ArticleCommentSettingsError("评论开关值无效。")
    try:
        thread, target = sync_article_thread(actor_id=actor, article_id=identity)
    except ArticleNotFound:
        raise ArticleCommentSettingsError from None
    if target.owner_id != actor:
        raise ArticleCommentSettingsError
    with transaction.atomic():
        locked = (
            DiscussionThread.objects.select_for_update()
            .filter(
                pk=thread.id,
                owner_id=actor,
                target_type=DiscussionTargetType.ARTICLE,
                target_id=identity,
                settings_revision_id=target.revision_id,
            )
            .first()
        )
        if locked is None:
            raise ArticleCommentSettingsError
        changed = locked.comments_enabled != enabled
        if changed:
            locked.comments_enabled = enabled
            locked.save(update_fields=("comments_enabled", "updated_at"))
    return ArticleCommentSettingsResult(identity, enabled, changed)
