from collections.abc import Callable

from apps.media.public import (
    SANITIZER_VERSION,
    TIPTAP_RENDERER_VERSION,
    TIPTAP_SCHEMA_FINGERPRINT,
    RenderingError,
    TipTapSchemaError,
    TrustedEmbedPolicy,
)

TrustedEmbedPolicyProvider = Callable[[], TrustedEmbedPolicy]


def _default_policy() -> TrustedEmbedPolicy:
    return TrustedEmbedPolicy()


_provider: TrustedEmbedPolicyProvider = _default_policy

_TIPTAP_CONTENT_ERRORS = {
    "media.tiptap.media_invalid.v1": (
        "content.media_invalid.v1",
        "正文媒体引用无效。",
    ),
    "media.tiptap.source_limit.v1": (
        "content.body_too_large.v1",
        "正文内容过大。",
    ),
}
_BODY_INVALID = ("content.body_invalid.v1", "正文格式不合法。")


def configure_content_embed_policy_provider(
    provider: TrustedEmbedPolicyProvider,
) -> None:
    if not callable(provider):
        raise TypeError("content embed policy provider must be callable")
    global _provider
    _provider = provider


def configured_content_embed_policy() -> TrustedEmbedPolicy:
    policy = _provider()
    if not isinstance(policy, TrustedEmbedPolicy):
        raise TypeError("content embed policy provider returned an invalid value")
    return policy


def content_rendering_version() -> str:
    fingerprint = configured_content_embed_policy().fingerprint[:16]
    return (
        f"{SANITIZER_VERSION}-{TIPTAP_SCHEMA_FINGERPRINT}-"
        f"{TIPTAP_RENDERER_VERSION}-p{fingerprint}"
    )


def content_error_for_rendering(error: BaseException) -> tuple[str, str]:
    if isinstance(error, TipTapSchemaError):
        return _TIPTAP_CONTENT_ERRORS.get(error.code, _BODY_INVALID)
    if isinstance(error, (RenderingError, TypeError, ValueError, RecursionError)):
        return _BODY_INVALID
    raise TypeError("error is not a rendering failure")


__all__ = [
    "configure_content_embed_policy_provider",
    "configured_content_embed_policy",
    "content_error_for_rendering",
    "content_rendering_version",
]
