from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.db import transaction

from apps.operations.public import record_audit_entry

from ..models import DiscussionThread
from ..ports import CommentAccountPolicy, default_comment_account_policy
from .threads import sync_guestbook_thread


class GuestbookSettingsError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class GuestbookSettingsResult:
    thread_id: str
    comments_enabled: bool
    post_login_required: bool
    changed: bool


def _actor_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise GuestbookSettingsError(
            "comments.guestbook_manage_forbidden.v1",
            "当前账户无法管理留言板。",
        ) from None


def _client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise GuestbookSettingsError(
            "comments.network_invalid.v1",
            "当前网络信息无效。",
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _flag(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise GuestbookSettingsError(
            "comments.guestbook_settings_invalid.v1",
            f"{field} 必须为布尔值。",
        )
    return value


def update_guestbook_settings(
    *,
    actor_id,
    comments_enabled,
    post_login_required,
    client_ip: str,
    trace_code: str,
    account_policy: CommentAccountPolicy | None = None,
) -> GuestbookSettingsResult:
    actor = _actor_id(actor_id)
    address = _client_ip(client_ip)
    enabled = _flag(comments_enabled, "留言开关")
    login_required = _flag(post_login_required, "登录要求")
    accounts = account_policy or default_comment_account_policy()
    if (
        accounts.is_ip_blocked(address)
        or not accounts.is_active_account(actor)
        or not accounts.is_administrator(actor)
    ):
        raise GuestbookSettingsError(
            "comments.guestbook_manage_forbidden.v1",
            "当前账户无法管理留言板。",
        )

    with transaction.atomic():
        synced = sync_guestbook_thread(account_policy=accounts)
        thread = DiscussionThread.objects.select_for_update().get(pk=synced.pk)
        before = {
            "comments_enabled": thread.comments_enabled,
            "post_login_required": thread.post_login_required,
        }
        after = {
            "comments_enabled": enabled,
            "post_login_required": login_required,
        }
        changed = before != after
        if changed:
            thread.comments_enabled = enabled
            thread.post_login_required = login_required
            thread.save(
                update_fields=(
                    "comments_enabled",
                    "post_login_required",
                    "updated_at",
                )
            )
            record_audit_entry(
                action="comments.guestbook.settings_update",
                actor_id=actor,
                target_id=str(thread.id),
                trace_code=trace_code,
                client_ip=address,
                before=before,
                after=after,
                summary="Administrator updated guestbook settings",
            )
    return GuestbookSettingsResult(
        thread_id=str(thread.id),
        comments_enabled=thread.comments_enabled,
        post_login_required=thread.post_login_required,
        changed=changed,
    )
