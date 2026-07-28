from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import transaction

from apps.core.events import enqueue_event
from apps.core.ids import normalize_ulid
from apps.core.time.clock import Clock, SystemClock, require_aware
from apps.operations.public import record_audit_entry

from ..events import COMMENT_DELETED
from ..models import Comment, DiscussionThread
from ..ports import (
    CommentAccountPolicy,
    CommentMediaGateway,
    default_comment_account_policy,
    default_comment_media_gateway,
)
from ..targets import DiscussionTargetType


class CommentDeletionError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class _DeletionMode(StrEnum):
    SELF = "SELF"
    OWNER = "OWNER"
    ADMIN = "ADMIN"


@dataclass(frozen=True, slots=True)
class CommentDeletionResult:
    comment_id: str
    changed: bool
    deleted_by_kind: str
    asset_ids: tuple[str, ...]
    recipient_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ReportCommentDeletionSnapshot:
    comment_id: str
    changed: bool
    body: str
    previous_state: str
    previous_visible_at: datetime
    asset_ids: tuple[str, ...]
    reported_author_id: UUID | None


@dataclass(frozen=True, slots=True)
class ReportCommentRecoveryResult:
    comment_id: str
    changed: bool
    state: str


class CommentReportRecoveryError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


def _actor_id(value) -> UUID:
    if value is None:
        raise CommentDeletionError(
            "comments.login_required.v1",
            "登录后才能删除评论。",
        )
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise CommentDeletionError(
            "comments.delete_not_allowed.v1",
            "当前评论无法删除。",
        ) from None


def _comment_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise CommentDeletionError(
            "comments.delete_not_allowed.v1",
            "当前评论无法删除。",
        ) from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise CommentDeletionError(
            "comments.network_invalid.v1",
            "当前网络信息无效。",
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def normalize_deletion_reason(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CommentDeletionError(
            "comments.deletion_reason_invalid.v1",
            "删除原因需为 200 个字符以内的纯文本。",
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return None
    if (
        len(normalized) > 200
        or "<" in normalized
        or ">" in normalized
        or "://" in normalized
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in normalized
        )
    ):
        raise CommentDeletionError(
            "comments.deletion_reason_invalid.v1",
            "删除原因需为 200 个字符以内的纯文本。",
        )
    return normalized


def _authorize_account(
    *,
    actor_id: UUID,
    client_ip: str,
    mode: _DeletionMode,
    account_policy: CommentAccountPolicy,
) -> None:
    if account_policy.is_ip_blocked(client_ip):
        raise CommentDeletionError(
            "comments.network_restricted.v1",
            "当前网络暂时受限。",
        )
    if not account_policy.is_active_account(actor_id):
        raise CommentDeletionError(
            "comments.account_unavailable.v1",
            "当前账户无法删除评论。",
        )
    if mode == _DeletionMode.ADMIN and not account_policy.is_administrator(actor_id):
        raise CommentDeletionError(
            "comments.delete_not_allowed.v1",
            "当前评论无法删除。",
        )


def _authorize_comment(
    *,
    actor_id: UUID,
    mode: _DeletionMode,
    account_policy: CommentAccountPolicy,
    thread: DiscussionThread,
    comment: Comment,
) -> None:
    if mode == _DeletionMode.SELF:
        allowed = (
            comment.author_kind == Comment.AuthorKind.ACCOUNT
            and comment.author_id == actor_id
        )
    elif mode == _DeletionMode.OWNER:
        allowed = thread.owner_id == actor_id and (
            thread.target_type != DiscussionTargetType.GUESTBOOK
            or account_policy.is_administrator(actor_id)
        )
    else:
        allowed = True
    if not allowed:
        raise CommentDeletionError(
            "comments.delete_not_allowed.v1",
            "当前评论无法删除。",
        )


def _asset_ids(media_gateway: CommentMediaGateway, comment_id: str) -> tuple[str, ...]:
    try:
        values = media_gateway.release_images(comment_id)
        if not isinstance(values, tuple):
            raise ValueError
        return tuple(normalize_ulid(value) for value in values)
    except Exception:
        raise CommentDeletionError(
            "comments.media_cleanup_failed.v1",
            "评论图片清理失败，请稍后重试。",
        ) from None


def _recipients(comment: Comment, thread: DiscussionThread) -> tuple[UUID, ...]:
    candidates = (
        comment.author_id
        if comment.author_kind == Comment.AuthorKind.ACCOUNT
        else None,
        thread.owner_id,
    )
    return tuple(dict.fromkeys(value for value in candidates if value is not None))


def _delete_comment(
    *,
    comment_id: str,
    actor_id,
    client_ip: str,
    trace_code: str,
    mode: _DeletionMode,
    expected_target_type: str | None = None,
    expected_target_id: str | None = None,
    reason=None,
    account_policy: CommentAccountPolicy | None = None,
    media_gateway: CommentMediaGateway | None = None,
    clock: Clock | None = None,
) -> CommentDeletionResult:
    identity = _comment_id(comment_id)
    actor = _actor_id(actor_id)
    address = _client_ip(client_ip)
    accounts = account_policy or default_comment_account_policy()
    media = media_gateway or default_comment_media_gateway()
    active_clock = clock or SystemClock()
    _authorize_account(
        actor_id=actor,
        client_ip=address,
        mode=mode,
        account_policy=accounts,
    )
    normalized_reason = (
        normalize_deletion_reason(reason) if mode == _DeletionMode.ADMIN else None
    )
    snapshot = Comment.objects.only("thread_id").filter(pk=identity).first()
    if snapshot is None:
        raise CommentDeletionError(
            "comments.delete_not_allowed.v1",
            "当前评论无法删除。",
        )
    with transaction.atomic():
        thread = DiscussionThread.objects.select_for_update().get(pk=snapshot.thread_id)
        comment = Comment.objects.select_for_update().get(pk=identity, thread=thread)
        if expected_target_type is not None and (
            thread.target_type != expected_target_type
            or thread.target_id != expected_target_id
        ):
            raise CommentDeletionError(
                "comments.delete_not_allowed.v1",
                "当前评论无法删除。",
            )
        _authorize_comment(
            actor_id=actor,
            mode=mode,
            account_policy=accounts,
            thread=thread,
            comment=comment,
        )
        if comment.state == Comment.State.DELETED:
            return CommentDeletionResult(
                comment.id,
                False,
                comment.deleted_by_kind,
                (),
                (),
            )
        before_state = comment.state
        comment.state = Comment.State.DELETED
        comment.body = ""
        comment.deleted_by_kind = mode.value
        comment.deletion_reason = normalized_reason
        comment.save(
            update_fields=(
                "state",
                "body",
                "deleted_by_kind",
                "deletion_reason",
                "updated_at",
            )
        )
        released_assets = _asset_ids(media, comment.id)
        recipient_ids = (
            _recipients(comment, thread) if mode == _DeletionMode.ADMIN else ()
        )
        if mode == _DeletionMode.ADMIN:
            record_audit_entry(
                action="comments.comment.admin_delete",
                actor_id=actor,
                target_id=comment.id,
                trace_code=trace_code,
                client_ip=address,
                before={
                    "state": before_state,
                    "author_kind": comment.author_kind,
                    "image_count": len(released_assets),
                },
                after={
                    "state": Comment.State.DELETED,
                    "deleted_by_kind": mode.value,
                    "image_count": len(released_assets),
                    "reason_provided": normalized_reason is not None,
                },
                summary="Administrator deleted comment",
            )
        enqueue_event(
            COMMENT_DELETED,
            aggregate_type="comment",
            aggregate_id=comment.id,
            actor_id=actor,
            trace_code=trace_code,
            payload={
                "thread_id": str(thread.id),
                "target_type": thread.target_type,
                "target_id": thread.target_id,
                "comment_id": comment.id,
                "deleted_by_kind": mode.value,
                "recipient_ids": [str(value) for value in recipient_ids],
                "reason": normalized_reason,
            },
            clock=active_clock,
        )
    return CommentDeletionResult(
        comment.id,
        True,
        mode.value,
        released_assets,
        recipient_ids,
    )


def delete_own_comment(**kwargs) -> CommentDeletionResult:
    return _delete_comment(mode=_DeletionMode.SELF, **kwargs)


def delete_comment_as_owner(**kwargs) -> CommentDeletionResult:
    return _delete_comment(mode=_DeletionMode.OWNER, **kwargs)


def delete_article_comment_as_owner(
    *, article_id: str, **kwargs
) -> CommentDeletionResult:
    try:
        target_id = normalize_ulid(article_id)
    except (TypeError, ValueError):
        raise CommentDeletionError(
            "comments.delete_not_allowed.v1",
            "当前评论无法删除。",
        ) from None
    return _delete_comment(
        mode=_DeletionMode.OWNER,
        expected_target_type=DiscussionTargetType.ARTICLE,
        expected_target_id=target_id,
        **kwargs,
    )


def delete_comment_as_admin(**kwargs) -> CommentDeletionResult:
    return _delete_comment(mode=_DeletionMode.ADMIN, **kwargs)


def delete_comment_for_report(
    *,
    comment_id: str,
    actor_id,
    client_ip: str,
    account_policy: CommentAccountPolicy | None = None,
    media_gateway: CommentMediaGateway | None = None,
) -> ReportCommentDeletionSnapshot:
    identity = _comment_id(comment_id)
    actor = _actor_id(actor_id)
    address = _client_ip(client_ip)
    accounts = account_policy or default_comment_account_policy()
    media = media_gateway or default_comment_media_gateway()
    _authorize_account(
        actor_id=actor,
        client_ip=address,
        mode=_DeletionMode.ADMIN,
        account_policy=accounts,
    )

    with transaction.atomic():
        comment = Comment.objects.select_for_update().filter(pk=identity).first()
        if comment is None:
            raise CommentDeletionError(
                "comments.delete_not_allowed.v1",
                "当前评论无法删除。",
            )
        if comment.state == Comment.State.DELETED:
            return ReportCommentDeletionSnapshot(
                comment_id=comment.id,
                changed=False,
                body="",
                previous_state=comment.state,
                previous_visible_at=comment.visible_at,
                asset_ids=(),
                reported_author_id=comment.author_id,
            )

        body = comment.body
        previous_state = comment.state
        previous_visible_at = comment.visible_at
        reported_author_id = comment.author_id
        comment.state = Comment.State.DELETED
        comment.body = ""
        comment.deleted_by_kind = Comment.DeletedByKind.REPORT
        comment.deletion_reason = None
        comment.save(
            update_fields=(
                "state",
                "body",
                "deleted_by_kind",
                "deletion_reason",
                "updated_at",
            )
        )
        released_assets = _asset_ids(media, comment.id)

    return ReportCommentDeletionSnapshot(
        comment_id=comment.id,
        changed=True,
        body=body,
        previous_state=previous_state,
        previous_visible_at=previous_visible_at,
        asset_ids=released_assets,
        reported_author_id=reported_author_id,
    )


def restore_comment_from_report(
    *,
    comment_id: str,
    actor_id,
    client_ip: str,
    body: str,
    previous_state: str,
    previous_visible_at: datetime,
    account_policy: CommentAccountPolicy | None = None,
) -> ReportCommentRecoveryResult:
    identity = _comment_id(comment_id)
    actor = _actor_id(actor_id)
    address = _client_ip(client_ip)
    accounts = account_policy or default_comment_account_policy()
    _authorize_account(
        actor_id=actor,
        client_ip=address,
        mode=_DeletionMode.ADMIN,
        account_policy=accounts,
    )
    if (
        not isinstance(body, str)
        or not 1 <= len(body) <= 100
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in body
        )
        or previous_state not in {Comment.State.BUFFERED, Comment.State.VISIBLE}
    ):
        raise CommentReportRecoveryError(
            "comments.report_recovery_snapshot_invalid.v1",
            "评论恢复材料无效。",
        )
    try:
        visible_at = require_aware(previous_visible_at)
    except (TypeError, ValueError, AttributeError):
        raise CommentReportRecoveryError(
            "comments.report_recovery_snapshot_invalid.v1",
            "评论恢复材料无效。",
        ) from None

    with transaction.atomic():
        comment = Comment.objects.select_for_update().filter(pk=identity).first()
        if comment is None:
            raise CommentReportRecoveryError(
                "comments.report_recovery_target_missing.v1",
                "评论当前无法恢复。",
            )
        if (
            comment.state != Comment.State.DELETED
            or comment.deleted_by_kind != Comment.DeletedByKind.REPORT
        ):
            raise CommentReportRecoveryError(
                "comments.report_recovery_state_conflict.v1",
                "评论当前无法恢复。",
            )
        comment.state = previous_state
        comment.body = body
        comment.visible_at = visible_at
        comment.deleted_by_kind = None
        comment.deletion_reason = None
        comment.save(
            update_fields=(
                "state",
                "body",
                "visible_at",
                "deleted_by_kind",
                "deletion_reason",
                "updated_at",
            )
        )
    return ReportCommentRecoveryResult(comment.id, True, comment.state)
