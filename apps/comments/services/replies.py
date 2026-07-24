from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F

from apps.core.events import enqueue_event
from apps.core.ids import new_ulid
from apps.core.time.clock import Clock, SystemClock

from ..constants import ACCOUNT_COOLDOWN_SECONDS, COMMENT_BUFFER_SECONDS
from ..cooldown import (
    CommentCooldownActive,
    CommentCooldownStore,
    default_comment_cooldown_store,
)
from ..errors import CommentPostingError
from ..events import COMMENT_CREATED, COMMENT_DEEP_THREAD
from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..validation import normalize_comment_body
from .access import resolve_reply_posting_access


@dataclass(frozen=True, slots=True)
class ReplyCommentResult:
    comment_id: str
    thread_id: str
    parent_id: str
    root_id: str
    state: str
    depth: int
    visible_at: datetime


def reply_to_comment(
    *,
    parent_id: str,
    actor_id,
    client_ip: str,
    body: str,
    trace_code: str,
    image_refs: tuple[str, ...] = (),
    clock: Clock | None = None,
    account_policy: CommentAccountPolicy | None = None,
    cooldown_store: CommentCooldownStore | None = None,
) -> ReplyCommentResult:
    normalized_body = normalize_comment_body(body)
    if not isinstance(image_refs, tuple) or image_refs:
        raise CommentPostingError(
            "comments.reply_images_forbidden.v1",
            "回复不能添加图片。",
            field="images",
        )
    accounts = account_policy or default_comment_account_policy()
    cooldown = cooldown_store or default_comment_cooldown_store()
    active_clock = clock or SystemClock()
    reservation = None

    try:
        with transaction.atomic():
            access = resolve_reply_posting_access(
                parent_id=parent_id,
                actor_id=actor_id,
                client_ip=client_ip,
                account_policy=accounts,
            )
            try:
                reservation = cooldown.reserve(
                    subject_kind="ACCOUNT",
                    subject_value=str(access.actor_id),
                    ttl_seconds=ACCOUNT_COOLDOWN_SECONDS,
                )
            except CommentCooldownActive as exc:
                raise CommentPostingError(
                    "comments.cooldown_active.v1",
                    f"请等待 {exc.remaining_seconds} 秒后再发表评论。",
                    retry_after=exc.remaining_seconds,
                ) from None

            parent = access.parent
            root = (
                parent
                if parent.parent_id is None
                else Comment.objects.select_for_update().get(
                    pk=parent.root_id,
                    thread=access.thread,
                    parent__isnull=True,
                )
            )
            now = active_clock.now()
            depth = parent.depth + 1
            comment = Comment.objects.create(
                id=new_ulid(),
                thread=access.thread,
                parent=parent,
                root=root,
                author_id=access.actor_id,
                author_kind=Comment.AuthorKind.ACCOUNT,
                body=normalized_body,
                state=Comment.State.BUFFERED,
                visible_at=now + timedelta(seconds=COMMENT_BUFFER_SECONDS),
                depth=depth,
                reply_count=0,
                client_ip=access.client_ip,
                created_at=now,
            )
            Comment.objects.filter(pk=root.pk).update(
                reply_count=F("reply_count") + 1,
                updated_at=now,
            )
            enqueue_event(
                COMMENT_CREATED,
                aggregate_type="comment",
                aggregate_id=comment.id,
                actor_id=access.actor_id,
                trace_code=trace_code,
                payload={
                    "thread_id": str(access.thread.id),
                    "target_type": access.target_type.value,
                    "target_id": access.target_id,
                    "author_kind": comment.author_kind,
                    "visible_at": comment.visible_at.isoformat(),
                    "image_count": 0,
                },
                clock=active_clock,
            )
            if depth > 100 and access.thread.deep_thread_alerted_at is None:
                access.thread.deep_thread_alerted_at = now
                access.thread.save(
                    update_fields=("deep_thread_alerted_at", "updated_at")
                )
                enqueue_event(
                    COMMENT_DEEP_THREAD,
                    aggregate_type="discussion_thread",
                    aggregate_id=str(access.thread.id),
                    actor_id=access.actor_id,
                    trace_code=trace_code,
                    payload={
                        "thread_id": str(access.thread.id),
                        "target_type": access.target_type.value,
                        "target_id": access.target_id,
                        "owner_id": str(access.thread.owner_id),
                        "root_id": root.id,
                        "depth": depth,
                    },
                    clock=active_clock,
                )
    except Exception:
        if reservation is not None:
            cooldown.rollback(reservation)
        raise

    return ReplyCommentResult(
        comment_id=comment.id,
        thread_id=str(access.thread.id),
        parent_id=parent.id,
        root_id=root.id,
        state=comment.state,
        depth=comment.depth,
        visible_at=comment.visible_at,
    )
