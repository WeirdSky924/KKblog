from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from django.core.exceptions import ValidationError

from .models.constants import MediaPurpose, MediaTargetType


class TargetAccessOperation(StrEnum):
    BIND = "bind"
    READ = "read"


@dataclass(frozen=True, slots=True)
class TargetAccessRequest:
    actor_id: UUID | None
    target_id: str
    purpose: MediaPurpose
    operation: TargetAccessOperation


@dataclass(frozen=True, slots=True)
class TargetAccessDecision:
    exists: bool
    can_bind: bool
    can_read: bool
    public_immutable: bool
    binding_scope: str | None = None


TargetAccessPort = Callable[[TargetAccessRequest], TargetAccessDecision]


class TargetAccessRegistry:
    def __init__(self) -> None:
        self._ports: dict[MediaTargetType, TargetAccessPort] = {}

    def register(
        self,
        target_type: MediaTargetType | str,
        port: TargetAccessPort,
        *,
        replace: bool = False,
    ) -> None:
        try:
            normalized = MediaTargetType(target_type)
        except (TypeError, ValueError):
            raise ValidationError("未注册的媒体目标类型") from None
        if not callable(port):
            raise TypeError("target access port must be callable")
        if normalized in self._ports and not replace:
            raise ValueError(f"Target access port already registered: {normalized}")
        self._ports[normalized] = port

    def decide(
        self,
        target_type: MediaTargetType | str,
        request: TargetAccessRequest,
    ) -> TargetAccessDecision:
        try:
            normalized = MediaTargetType(target_type)
            port = self._ports[normalized]
        except (KeyError, TypeError, ValueError):
            raise ValidationError("媒体目标尚未提供访问端口") from None
        decision = port(request)
        if not isinstance(decision, TargetAccessDecision):
            raise TypeError("target access port returned an invalid decision")
        return decision


default_target_access_registry = TargetAccessRegistry()


def register_target_access(
    target_type: MediaTargetType | str,
    port: TargetAccessPort,
    *,
    replace: bool = False,
) -> None:
    default_target_access_registry.register(target_type, port, replace=replace)


_PURPOSE_TARGETS: Mapping[MediaPurpose, frozenset[MediaTargetType]] = {
    MediaPurpose.AVATAR: frozenset({MediaTargetType.ACCOUNT_PROFILE}),
    MediaPurpose.COVER: frozenset({MediaTargetType.ARTICLE_REVISION}),
    MediaPurpose.SECTION_COVER: frozenset({MediaTargetType.SECTION}),
    MediaPurpose.BODY: frozenset({MediaTargetType.ARTICLE_REVISION}),
    MediaPurpose.ATTACHMENT: frozenset({MediaTargetType.ARTICLE_REVISION}),
    MediaPurpose.COMMENT: frozenset({MediaTargetType.COMMENT}),
    MediaPurpose.EVIDENCE: frozenset(
        {
            MediaTargetType.REPORT,
            MediaTargetType.REPORT_APPEAL,
            MediaTargetType.ARTICLE_APPEAL,
        }
    ),
    MediaPurpose.LOGO: frozenset({MediaTargetType.SITE_BRAND}),
    MediaPurpose.HERO: frozenset({MediaTargetType.SITE_BRAND}),
    MediaPurpose.FRIEND_LOGO: frozenset(),
    MediaPurpose.IMPORT: frozenset({MediaTargetType.IMPORT_JOB}),
}


def validate_binding_target(
    purpose: MediaPurpose | str, target_type: MediaTargetType | str
) -> MediaTargetType:
    try:
        normalized_purpose = MediaPurpose(purpose)
        normalized_target = MediaTargetType(target_type)
    except (TypeError, ValueError):
        raise ValidationError("未注册的媒体用途或目标类型") from None
    if normalized_target not in _PURPOSE_TARGETS[normalized_purpose]:
        raise ValidationError("媒体用途与目标类型不匹配")
    return normalized_target


def registered_target_types() -> tuple[str, ...]:
    return tuple(choice.value for choice in MediaTargetType)
