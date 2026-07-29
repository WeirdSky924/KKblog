import unicodedata
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve

PUBLIC_NAMESPACES = frozenset({"article", "public"})


def normalize_navigation_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("导航名称不合法。")
    label = unicodedata.normalize("NFKC", value).strip()
    if not label or len(label) > 80 or any(ord(character) < 32 for character in label):
        raise ValueError("导航名称须为 1 至 80 个字符。")
    return label


def _value(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("导航目标不合法。")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 255
        or any(character in normalized for character in ("\\", "\r", "\n", "\x00"))
    ):
        raise ValueError("导航目标不合法。")
    return normalized


def normalize_internal_navigation_url(value: str) -> str:
    normalized = _value(value)
    parsed = urlsplit(normalized)
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
    ):
        raise ValueError("站内页必须使用公开站内路径。")
    try:
        match = resolve(parsed.path)
    except Resolver404:
        raise ValueError("站内页路径不存在。") from None
    if match.namespace not in PUBLIC_NAMESPACES:
        raise ValueError("站内页只能指向公开页面。")
    return normalized


def normalize_external_navigation_url(value: str) -> str:
    normalized = _value(value)
    parsed = urlsplit(normalized)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("外链地址不合法。") from None
    del port
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
    ):
        raise ValueError("外链必须使用不含凭据的 HTTPS 地址。")
    return normalized


def require_safe_navigation_url(value: str) -> None:
    normalized = _value(value)
    parsed = urlsplit(normalized)
    if parsed.scheme == "https":
        normalize_external_navigation_url(normalized)
        return
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or parsed.scheme
        or parsed.netloc
    ):
        raise ValueError("URL must be a safe site-relative or HTTPS URL")


__all__ = [
    "normalize_external_navigation_url",
    "normalize_internal_navigation_url",
    "normalize_navigation_label",
    "require_safe_navigation_url",
]
