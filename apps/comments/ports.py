from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from django.conf import settings
from django.utils.module_loading import import_string


class CommentAccountPolicy(Protocol):
    def is_active_account(self, account_id: UUID | None) -> bool: ...

    def is_administrator(self, account_id: UUID | None) -> bool: ...

    def is_ip_blocked(self, client_ip: str) -> bool: ...

    def public_identity(self, account_id: UUID) -> "CommentAuthorIdentity | None": ...

    def public_identities(
        self, account_ids: tuple[UUID, ...]
    ) -> dict[UUID, "CommentAuthorIdentity"]: ...


@dataclass(frozen=True, slots=True)
class CommentAuthorIdentity:
    account_id: UUID
    display_name: str
    profile_url: str


@dataclass(frozen=True, slots=True)
class CommentAuthorPresentation:
    label: str
    profile_url: str | None


class CommentMediaError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class CommentImageUpload:
    asset_id: str
    image_ref: str


class CommentMediaGateway(Protocol):
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
    ) -> CommentImageUpload: ...

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
    ) -> tuple[str, ...]: ...

    def bound_image_ids(
        self, comment_ids: tuple[str, ...]
    ) -> dict[str, tuple[str, ...]]: ...

    def release_images(self, comment_id: str) -> tuple[str, ...]: ...


def _provider(setting_name: str):
    path = getattr(settings, setting_name, "")
    if not isinstance(path, str) or not path:
        raise RuntimeError(f"Missing provider setting: {setting_name}")
    provider = import_string(path)
    value = provider()
    return value


def default_comment_account_policy() -> CommentAccountPolicy:
    return _provider("COMMENTS_ACCOUNT_POLICY_PROVIDER")


def default_comment_media_gateway() -> CommentMediaGateway:
    return _provider("COMMENTS_MEDIA_GATEWAY_PROVIDER")
