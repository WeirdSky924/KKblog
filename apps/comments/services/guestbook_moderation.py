from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.core.ids import normalize_ulid
from apps.operations.public import record_audit_entry

from ..models import Comment
from ..ports import CommentAccountPolicy, default_comment_account_policy
from ..targets import DiscussionTargetType


class GuestbookModerationError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class GuestbookModerationResult:
    comment_id: str
    operation: str
    hidden: bool
    flag: str


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise GuestbookModerationError(
            "comments.guestbook_manage_forbidden.v1",
            "当前账户无法管理留言板。",
        ) from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise GuestbookModerationError(
            "comments.network_invalid.v1", "当前网络信息无效。"
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def moderate_guestbook_comment(
    *,
    actor_id,
    comment_id: str,
    operation: str,
    flag: str = "",
    client_ip: str,
    trace_code: str,
    account_policy: CommentAccountPolicy | None = None,
) -> GuestbookModerationResult:
    actor = _actor_id(actor_id)
    address = _client_ip(client_ip)
    accounts = account_policy or default_comment_account_policy()
    if accounts.is_ip_blocked(address) or not accounts.is_administrator(actor):
        raise GuestbookModerationError(
            "comments.guestbook_manage_forbidden.v1",
            "当前账户无法管理留言板。",
        )
    if operation not in {"HIDE", "SHOW", "MARK"}:
        raise GuestbookModerationError(
            "comments.guestbook_operation_invalid.v1", "留言板操作无效。"
        )
    if flag not in {"", *Comment.GuestbookFlag.values}:
        raise GuestbookModerationError(
            "comments.guestbook_flag_invalid.v1", "留言标记无效。"
        )
    try:
        identity = normalize_ulid(comment_id)
    except (TypeError, ValueError):
        raise GuestbookModerationError(
            "comments.guestbook_comment_missing.v1", "留言不存在。"
        ) from None

    with transaction.atomic():
        comment = (
            Comment.objects.select_for_update()
            .select_related("thread")
            .filter(
                pk=identity,
                parent__isnull=True,
                thread__target_type=DiscussionTargetType.GUESTBOOK.value,
                thread__target_id="site",
            )
            .first()
        )
        if comment is None or comment.state == Comment.State.DELETED:
            raise GuestbookModerationError(
                "comments.guestbook_comment_missing.v1", "留言不存在或已删除。"
            )
        before = {
            "hidden": comment.guestbook_hidden,
            "flag": comment.guestbook_flag,
        }
        if operation == "HIDE":
            comment.guestbook_hidden = True
            comment.guestbook_hidden_at = timezone.now()
            comment.guestbook_hidden_by_id = actor
        elif operation == "SHOW":
            comment.guestbook_hidden = False
            comment.guestbook_hidden_at = None
            comment.guestbook_hidden_by_id = None
        else:
            comment.guestbook_flag = flag
        after = {
            "hidden": comment.guestbook_hidden,
            "flag": comment.guestbook_flag,
        }
        if before != after:
            comment.save(
                update_fields=(
                    "guestbook_hidden",
                    "guestbook_flag",
                    "guestbook_hidden_at",
                    "guestbook_hidden_by",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="comments.guestbook.moderate",
                actor_id=actor,
                target_id=comment.id,
                trace_code=trace_code,
                client_ip=address,
                before=before,
                after={**after, "operation": operation},
                summary="Administrator moderated guestbook comment",
            )
    return GuestbookModerationResult(
        comment_id=identity,
        operation=operation,
        hidden=comment.guestbook_hidden,
        flag=comment.guestbook_flag,
    )
