from collections.abc import Iterable

from ..ports import (
    CommentAccountPolicy,
    CommentImageUpload,
    CommentMediaGateway,
    default_comment_account_policy,
    default_comment_media_gateway,
)
from .access import resolve_top_level_posting_access


def stage_top_level_comment_image(
    *,
    target_type,
    target_id: str,
    actor_id,
    client_ip: str,
    original_name: str,
    declared_content_type: str,
    chunks: Iterable[bytes],
    account_policy: CommentAccountPolicy | None = None,
    media_gateway: CommentMediaGateway | None = None,
) -> CommentImageUpload:
    accounts = account_policy or default_comment_account_policy()
    media = media_gateway or default_comment_media_gateway()
    access = resolve_top_level_posting_access(
        target_type=target_type,
        target_id=target_id,
        actor_id=actor_id,
        client_ip=client_ip,
        account_policy=accounts,
    )
    return media.stage_image(
        actor_id=access.actor_id,
        thread_owner_id=access.thread.owner_id,
        target_type=access.target_type.value,
        target_id=access.target_id,
        client_ip=access.client_ip,
        original_name=original_name,
        declared_content_type=declared_content_type,
        chunks=chunks,
    )
