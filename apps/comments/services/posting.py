from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.events import enqueue_event
from apps.core.ids import new_ulid
from apps.core.time.clock import Clock, SystemClock

from ..constants import (
    ACCOUNT_COOLDOWN_SECONDS,
    ANONYMOUS_COOLDOWN_SECONDS,
    COMMENT_BUFFER_SECONDS,
)
from ..cooldown import (
    CommentCooldownActive,
    CommentCooldownStore,
    default_comment_cooldown_store,
)
from ..errors import CommentPostingError
from ..events import COMMENT_CREATED
from ..models import Comment
from ..ports import (
    CommentAccountPolicy,
    CommentMediaError,
    CommentMediaGateway,
    default_comment_account_policy,
    default_comment_media_gateway,
)
from ..targets import DiscussionTargetType
from ..validation import normalize_comment_body, normalize_guestbook_body
from .access import resolve_top_level_posting_access


@dataclass(frozen=True, slots=True)
class TopLevelCommentResult:
    comment_id: str
    thread_id: str
    state: str
    visible_at: datetime
    image_count: int


def _image_refs(values) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        try:
            values = tuple(values)
        except TypeError:
            values = ()
    if (
        len(values) > 3
        or len(set(values)) != len(values)
        or any(
            not isinstance(value, str) or not 1 <= len(value) <= 2_048
            for value in values
        )
    ):
        raise CommentPostingError(
            "comments.images_invalid.v1",
            "顶层评论最多使用三张有效图片。",
            field="images",
        )
    return values


def create_top_level_comment(
    *,
    target_type,
    target_id: str,
    actor_id,
    client_ip: str,
    body: str,
    image_refs: tuple[str, ...] = (),
    trace_code: str,
    clock: Clock | None = None,
    account_policy: CommentAccountPolicy | None = None,
    cooldown_store: CommentCooldownStore | None = None,
    media_gateway: CommentMediaGateway | None = None,
    strict_guestbook: bool = False,
) -> TopLevelCommentResult:
    is_guestbook = (
        target_type == DiscussionTargetType.GUESTBOOK or target_type == "GUESTBOOK"
    )
    is_strict_guestbook = is_guestbook and strict_guestbook
    normalized_body = (
        normalize_guestbook_body(body)
        if is_strict_guestbook
        else normalize_comment_body(body)
    )
    if is_strict_guestbook and image_refs:
        raise CommentPostingError(
            "comments.images_invalid.v1",
            "留言板仅支持纯文字留言。",
            field="images",
        )
    normalized_refs = _image_refs(image_refs) if not is_strict_guestbook else ()
    accounts = account_policy or default_comment_account_policy()
    cooldown = cooldown_store or default_comment_cooldown_store()
    media = media_gateway or default_comment_media_gateway()
    active_clock = clock or SystemClock()

    reservation = None
    try:
        with transaction.atomic():
            access = resolve_top_level_posting_access(
                target_type=target_type,
                target_id=target_id,
                actor_id=actor_id,
                client_ip=client_ip,
                account_policy=accounts,
            )
            thread = access.thread
            actor = access.actor_id
            address = access.client_ip

            now = active_clock.now()
            is_guestbook = access.target_type is DiscussionTargetType.GUESTBOOK
            is_strict_guestbook = is_guestbook and strict_guestbook
            if is_strict_guestbook:
                if actor is None:
                    raise CommentPostingError(
                        "comments.login_required.v1", "登录后才能发表留言。"
                    )
                local_now = timezone.localtime(now)
                day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                daily_comments = Comment.objects.filter(
                    thread=thread,
                    parent__isnull=True,
                    created_at__gte=day_start,
                    created_at__lt=day_end,
                )
                if daily_comments.count() >= thread.guestbook_daily_limit:
                    raise CommentPostingError(
                        "comments.guestbook_daily_limit.v1",
                        "今日留言板已满，请明天再来。",
                        field="body",
                    )
                if (
                    daily_comments.filter(
                        author_id=actor,
                        author_kind=Comment.AuthorKind.ACCOUNT,
                    ).count()
                    >= thread.guestbook_account_daily_limit
                ):
                    raise CommentPostingError(
                        "comments.guestbook_account_daily_limit.v1",
                        f"每位用户每天最多留言 {thread.guestbook_account_daily_limit} 条。",
                        field="body",
                    )
            else:
                ttl = (
                    ACCOUNT_COOLDOWN_SECONDS
                    if actor is not None
                    else ANONYMOUS_COOLDOWN_SECONDS
                )
                try:
                    reservation = cooldown.reserve(
                        subject_kind="ACCOUNT" if actor is not None else "IP",
                        subject_value=str(actor) if actor is not None else address,
                        ttl_seconds=ttl,
                    )
                except CommentCooldownActive as exc:
                    raise CommentPostingError(
                        "comments.cooldown_active.v1",
                        f"请等待 {exc.remaining_seconds} 秒后再发表评论。",
                        retry_after=exc.remaining_seconds,
                    ) from None
            comment_id = new_ulid()
            comment = Comment.objects.create(
                id=comment_id,
                thread=thread,
                parent=None,
                root_id=comment_id,
                author_id=actor,
                author_kind=(
                    Comment.AuthorKind.ACCOUNT
                    if actor is not None
                    else Comment.AuthorKind.ANONYMOUS
                ),
                body=normalized_body,
                state=(
                    Comment.State.VISIBLE
                    if is_strict_guestbook
                    else Comment.State.BUFFERED
                ),
                visible_at=(
                    now
                    if is_strict_guestbook
                    else now + timedelta(seconds=COMMENT_BUFFER_SECONDS)
                ),
                depth=0,
                reply_count=0,
                client_ip=address,
                created_at=now,
            )
            try:
                asset_ids = (
                    media.bind_images(
                        actor_id=actor,
                        thread_owner_id=thread.owner_id,
                        target_type=access.target_type.value,
                        target_id=access.target_id,
                        comment_id=comment.id,
                        client_ip=address,
                        image_refs=normalized_refs,
                    )
                    if normalized_refs
                    else ()
                )
            except CommentMediaError as exc:
                raise CommentPostingError(
                    "comments.images_invalid.v1", exc.safe_message, field="images"
                ) from None
            enqueue_event(
                COMMENT_CREATED,
                aggregate_type="comment",
                aggregate_id=comment.id,
                actor_id=actor,
                trace_code=trace_code,
                payload={
                    "thread_id": str(thread.id),
                    "target_type": access.target_type.value,
                    "target_id": access.target_id,
                    "author_kind": comment.author_kind,
                    "visible_at": comment.visible_at.isoformat(),
                    "image_count": len(asset_ids),
                },
                clock=active_clock,
            )
    except Exception:
        if reservation is not None:
            cooldown.rollback(reservation)
        raise

    return TopLevelCommentResult(
        comment_id=comment.id,
        thread_id=str(thread.id),
        state=comment.state,
        visible_at=comment.visible_at,
        image_count=len(asset_ids),
    )
