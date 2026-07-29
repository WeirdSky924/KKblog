from collections.abc import Callable

from apps.media.public import SANITIZER_VERSION, TrustedEmbedPolicy

TrustedEmbedPolicyProvider = Callable[[], TrustedEmbedPolicy]


def _default_policy() -> TrustedEmbedPolicy:
    return TrustedEmbedPolicy()


_provider: TrustedEmbedPolicyProvider = _default_policy


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
    return f"{SANITIZER_VERSION}-p{fingerprint}"


__all__ = [
    "configure_content_embed_policy_provider",
    "configured_content_embed_policy",
    "content_rendering_version",
]
