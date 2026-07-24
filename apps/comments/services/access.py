from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from apps.content.public import ArticleLoginRequired, ArticleNotFound

from ..errors import CommentPostingError
from ..models import DiscussionThread
from ..ports import CommentAccountPolicy
from ..targets import (
    DiscussionTargetError,
    DiscussionTargetType,
    normalize_target,
)
from .threads import sync_article_thread


@dataclass(frozen=True, slots=True)
class TopLevelPostingAccess:
    thread: DiscussionThread
    target_type: DiscussionTargetType
    target_id: str
    actor_id: UUID | None
    client_ip: str


def normalize_actor(value) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise CommentPostingError(
            "comments.account_unavailable.v1", "当前账户无法发表评论。"
        ) from None


def normalize_client_ip(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise CommentPostingError(
            "comments.network_invalid.v1", "当前网络信息无效。"
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _thread(*, target_type: DiscussionTargetType, target_id: str, actor_id):
    if target_type == DiscussionTargetType.ARTICLE:
        try:
            return sync_article_thread(actor_id=actor_id, article_id=target_id)[0]
        except ArticleLoginRequired:
            raise CommentPostingError(
                "comments.login_required.v1", "登录后才能发表评论。"
            ) from None
        except ArticleNotFound:
            raise CommentPostingError(
                "comments.target_not_found.v1", "未找到可评论的内容。"
            ) from None
    thread = (
        DiscussionThread.objects.select_for_update()
        .filter(target_type=target_type, target_id=target_id)
        .first()
    )
    if thread is None:
        raise CommentPostingError(
            "comments.target_not_found.v1", "未找到可评论的内容。"
        )
    return thread


def resolve_top_level_posting_access(
    *,
    target_type,
    target_id: str,
    actor_id,
    client_ip: str,
    account_policy: CommentAccountPolicy,
) -> TopLevelPostingAccess:
    try:
        target = normalize_target(target_type, target_id)
    except DiscussionTargetError:
        raise CommentPostingError(
            "comments.target_not_found.v1", "未找到可评论的内容。"
        ) from None
    actor = normalize_actor(actor_id)
    address = normalize_client_ip(client_ip)
    if account_policy.is_ip_blocked(address):
        raise CommentPostingError("comments.network_restricted.v1", "当前网络暂时受限")
    if actor is not None and not account_policy.is_active_account(actor):
        raise CommentPostingError(
            "comments.account_unavailable.v1", "当前账户无法发表评论。"
        )
    thread = _thread(
        target_type=target.target_type,
        target_id=target.target_id,
        actor_id=actor,
    )
    if not thread.comments_enabled:
        raise CommentPostingError("comments.closed.v1", "评论区当前已关闭。")
    if actor is None and thread.post_login_required:
        raise CommentPostingError("comments.login_required.v1", "登录后才能发表评论。")
    return TopLevelPostingAccess(
        thread=thread,
        target_type=target.target_type,
        target_id=target.target_id,
        actor_id=actor,
        client_ip=address,
    )
