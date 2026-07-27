import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.media.models import MediaPurpose

UploadAccessPort = Callable[[UUID | None], bool]
UploadTargetAccessPort = Callable[[UUID | None, str], bool]
_ADAPTER_KEY = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_QUERY_PARAMETER = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


@dataclass(frozen=True, slots=True)
class MediaUploadAdapter:
    key: str
    purpose: MediaPurpose
    input_name: str
    access: UploadAccessPort
    target_query_parameter: str | None = None
    target_access: UploadTargetAccessPort | None = None


class MediaUploadAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, MediaUploadAdapter] = {}

    def register(self, adapter: MediaUploadAdapter, *, replace: bool = False) -> None:
        if (
            not isinstance(adapter, MediaUploadAdapter)
            or _ADAPTER_KEY.fullmatch(adapter.key) is None
            or not adapter.input_name.isidentifier()
            or not callable(adapter.access)
            or (
                adapter.target_query_parameter is not None
                and _QUERY_PARAMETER.fullmatch(adapter.target_query_parameter) is None
            )
            or (
                (adapter.target_query_parameter is None)
                != (adapter.target_access is None)
            )
            or (
                adapter.target_access is not None
                and not callable(adapter.target_access)
            )
        ):
            raise ValidationError("媒体上传适配器不合法")
        try:
            MediaPurpose(adapter.purpose)
        except (TypeError, ValueError):
            raise ValidationError("媒体上传用途不合法") from None
        if adapter.key in self._adapters and not replace:
            raise ValueError(f"Media upload adapter already registered: {adapter.key}")
        self._adapters[adapter.key] = adapter

    def resolve(self, key: str) -> MediaUploadAdapter:
        try:
            return self._adapters[key]
        except (KeyError, TypeError):
            raise ValidationError("媒体上传入口不存在") from None


default_media_upload_adapters = MediaUploadAdapterRegistry()


def register_media_upload_adapter(
    adapter: MediaUploadAdapter, *, replace: bool = False
) -> None:
    default_media_upload_adapters.register(adapter, replace=replace)
