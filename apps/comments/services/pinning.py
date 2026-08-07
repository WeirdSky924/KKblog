from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, ProgrammingError, transaction
from django.utils import timezone

from apps.core.ids import normalize_ulid

from ..models import Comment, CommentPin, DiscussionThread
from ..ports import CommentAccountPolicy, default_comment_account_policy


class CommentPinError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class CommentPinUnavailableError(RuntimeError):
    code = "comments.pin_unavailable.v1"

    def __init__(self) -> None:
        self.safe_message = "评论置顶功能正在升级，请稍后再试。"
        super().__init__(self.safe_message)


@dataclass(frozen=True, slots=True)
class CommentPinState:
    comment_id: str
    thread_id: UUID
    pinned: bool
    changed: bool


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise CommentPinError(
            "comments.pin_forbidden.v1", "当前账户不能管理评论置顶。"
        ) from None


def _comment_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise CommentPinError(
            "comments.pin_invalid_target.v1", "该评论不能置顶。"
        ) from None


def _article_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise CommentPinError(
            "comments.pin_invalid_target.v1", "该评论不能置顶。"
        ) from None


def _is_missing_table(error: ProgrammingError) -> bool:
    return getattr(error.__cause__, "sqlstate", None) == "42P01"


def set_article_comment_pin(
    *,
    actor_id,
    comment_id: str,
    pinned: bool,
    article_id: str | None = None,
    account_policy: CommentAccountPolicy | None = None,
) -> CommentPinState:
    actor = _actor_id(actor_id)
    identity = _comment_id(comment_id)
    article = _article_id(article_id) if article_id is not None else None
    if type(pinned) is not bool:
        raise CommentPinError("comments.pin_invalid_state.v1", "评论置顶状态无效。")
    accounts = account_policy or default_comment_account_policy()
    try:
        with transaction.atomic():
            comment = (
                Comment.objects.select_related("thread")
                .select_for_update()
                .filter(pk=identity)
                .first()
            )
            if (
                comment is None
                or comment.thread.target_type != DiscussionThread.TargetType.ARTICLE
                or (article is not None and comment.thread.target_id != article)
                or comment.parent_id is not None
                or comment.state != Comment.State.VISIBLE
            ):
                raise CommentPinError(
                    "comments.pin_invalid_target.v1", "该评论不能置顶。"
                )
            thread = DiscussionThread.objects.select_for_update().get(
                pk=comment.thread_id
            )
            if not accounts.is_active_account(actor) or not (
                thread.owner_id == actor or accounts.is_administrator(actor)
            ):
                raise CommentPinError(
                    "comments.pin_forbidden.v1", "当前账户不能管理评论置顶。"
                )

            current = (
                CommentPin.objects.select_for_update()
                .filter(thread_id=thread.id)
                .first()
            )
            if pinned:
                if current is not None and current.comment_id == comment.id:
                    changed = False
                else:
                    if current is not None:
                        current.delete()
                    CommentPin.objects.create(
                        thread=thread,
                        comment=comment,
                        pinned_by_id=actor,
                        pinned_at=timezone.now(),
                    )
                    changed = True
            else:
                changed = bool(current is not None and current.comment_id == comment.id)
                if changed:
                    current.delete()
    except ProgrammingError as exc:
        if _is_missing_table(exc):
            raise CommentPinUnavailableError from None
        raise
    except IntegrityError:
        raise CommentPinError(
            "comments.pin_conflict.v1", "评论置顶状态已变化，请重试。"
        ) from None
    return CommentPinState(comment.id, thread.id, pinned, changed)
