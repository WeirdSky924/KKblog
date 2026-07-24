import hashlib
import hmac
from collections.abc import Iterable
from functools import partial
from ipaddress import IPv6Address, ip_address
from uuid import UUID

from django.conf import settings
from django.core import signing

from apps.accounts.public import is_active_account, is_administrator, is_ip_blocked
from apps.comments.policies import comment_media_access
from apps.comments.ports import CommentImageUpload, CommentMediaError
from apps.comments.targets import DiscussionTargetType, normalize_target
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    MediaPurpose,
    MediaTargetType,
    MediaUploadError,
    TargetAccessDecision,
    bind_assets,
    register_target_access,
    stage_upload,
)
from apps.media.storage import FilesystemMediaStorage
from apps.operations.public import require_image_creation_capacity

_IMAGE_REF_SALT = "comments.image-ref.v1"
_IMAGE_REF_MAX_AGE_SECONDS = 86_400


class _CommentAccountPolicy:
    is_active_account = staticmethod(is_active_account)
    is_administrator = staticmethod(is_administrator)
    is_ip_blocked = staticmethod(is_ip_blocked)


def comment_account_policy() -> _CommentAccountPolicy:
    return _CommentAccountPolicy()


def _actor(value) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise CommentMediaError(
            "comments.media_actor_invalid.v1", "当前身份无法上传图片。"
        ) from None


def _address(value: str) -> str:
    try:
        parsed = ip_address(value)
    except (TypeError, ValueError):
        raise CommentMediaError(
            "comments.media_network_invalid.v1", "当前网络信息无效。"
        ) from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return str(parsed)


def _subject_digest(actor_id: UUID | None, client_ip: str) -> str:
    subject = f"account:{actor_id}" if actor_id is not None else f"ip:{client_ip}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"comment-image:{subject}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _target(target_type: str, target_id: str) -> tuple[str, str]:
    try:
        normalized = normalize_target(target_type, target_id)
    except ValueError:
        raise CommentMediaError(
            "comments.media_target_invalid.v1", "图片归属内容无效。"
        ) from None
    return normalized.target_type.value, normalized.target_id


def _media_target_access(request) -> TargetAccessDecision:
    decision = comment_media_access(
        actor_id=request.actor_id,
        comment_id=request.target_id,
    )
    return TargetAccessDecision(
        exists=decision.exists,
        can_bind=decision.can_bind,
        can_read=decision.can_read,
        public_immutable=False,
    )


def _register_comment_media_target() -> None:
    register_target_access(
        MediaTargetType.COMMENT,
        _media_target_access,
        replace=True,
    )


class _CommentMediaGateway:
    def stage_image(
        self,
        *,
        actor_id: UUID | None,
        thread_owner_id: UUID,
        target_type: str,
        target_id: str,
        client_ip: str,
        original_name: str,
        declared_content_type: str,
        chunks: Iterable[bytes],
    ) -> CommentImageUpload:
        actor = _actor(actor_id)
        try:
            owner = UUID(str(actor or thread_owner_id))
        except (TypeError, ValueError):
            raise CommentMediaError(
                "comments.media_owner_invalid.v1", "图片归属账户无效。"
            ) from None
        address = _address(client_ip)
        normalized_type, normalized_id = _target(target_type, target_id)
        storage_target = (
            normalized_id if normalized_type == DiscussionTargetType.ARTICLE else "site"
        )
        try:
            asset = stage_upload(
                owner_id=owner,
                purpose=MediaPurpose.COMMENT,
                original_name=original_name,
                declared_content_type=declared_content_type,
                chunks=chunks,
                storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
                capacity_check=partial(
                    require_image_creation_capacity,
                    settings.MEDIA_ROOT,
                ),
                target_id=storage_target,
            )
        except MediaUploadError as exc:
            raise CommentMediaError(exc.code, exc.safe_message) from None
        image_ref = signing.dumps(
            {
                "v": 1,
                "asset_id": asset.id,
                "owner_id": str(owner),
                "target_type": normalized_type,
                "target_id": normalized_id,
                "subject": _subject_digest(actor, address),
            },
            salt=_IMAGE_REF_SALT,
            compress=True,
        )
        return CommentImageUpload(asset_id=asset.id, image_ref=image_ref)

    def bind_images(
        self,
        *,
        actor_id: UUID | None,
        thread_owner_id: UUID,
        target_type: str,
        target_id: str,
        comment_id: str,
        client_ip: str,
        image_refs: tuple[str, ...],
    ) -> tuple[str, ...]:
        actor = _actor(actor_id)
        address = _address(client_ip)
        normalized_type, normalized_id = _target(target_type, target_id)
        owner = actor or thread_owner_id
        subject = _subject_digest(actor, address)
        asset_ids = []
        expected_keys = {
            "v",
            "asset_id",
            "owner_id",
            "target_type",
            "target_id",
            "subject",
        }
        for image_ref in image_refs:
            try:
                payload = signing.loads(
                    image_ref,
                    salt=_IMAGE_REF_SALT,
                    max_age=_IMAGE_REF_MAX_AGE_SECONDS,
                )
            except signing.BadSignature:
                raise CommentMediaError(
                    "comments.media_ref_invalid.v1", "图片引用无效或已过期。"
                ) from None
            if (
                not isinstance(payload, dict)
                or set(payload) != expected_keys
                or payload["v"] != 1
                or payload["owner_id"] != str(owner)
                or payload["target_type"] != normalized_type
                or payload["target_id"] != normalized_id
                or payload["subject"] != subject
                or not isinstance(payload["asset_id"], str)
            ):
                raise CommentMediaError(
                    "comments.media_ref_invalid.v1", "图片引用与当前评论不匹配。"
                )
            asset_ids.append(payload["asset_id"])
        if len(set(asset_ids)) != len(asset_ids):
            raise CommentMediaError(
                "comments.media_ref_invalid.v1", "评论图片不能重复。"
            )
        _register_comment_media_target()
        try:
            bindings = bind_assets(
                actor_id=owner,
                target_type=MediaTargetType.COMMENT,
                target_id=comment_id,
                inputs=tuple(
                    BindingInput(asset_id=asset_id, slot=f"image-{index}")
                    for index, asset_id in enumerate(asset_ids, 1)
                ),
            )
        except MediaBindingError as exc:
            raise CommentMediaError(exc.code, exc.safe_message) from None
        return tuple(binding.asset_id for binding in bindings)


def comment_media_gateway() -> _CommentMediaGateway:
    _register_comment_media_target()
    return _CommentMediaGateway()


def configure_comment_integrations() -> None:
    _register_comment_media_target()
