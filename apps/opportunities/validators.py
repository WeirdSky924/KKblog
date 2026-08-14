import posixpath
import re
import unicodedata
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError

_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)
_IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{1,79}\Z")


def normalized_text(value: str, *, maximum: int, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field}不合法。")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if (
        not normalized
        or len(normalized) > maximum
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValidationError(f"{field}须为 1 至 {maximum} 个字符。")
    return normalized


def optional_text(value: str, *, maximum: int, field: str) -> str:
    if value in (None, ""):
        return ""
    return normalized_text(value, maximum=maximum, field=field)


def normalize_filter_label(value: str) -> tuple[str, str]:
    display = normalized_text(value, maximum=100, field="筛选值")
    normalized = display.casefold().replace("，", ",").replace("／", "/")
    return display, normalized


def normalize_opportunity_identity_title(value: str) -> str:
    return normalized_text(value, maximum=200, field="岗位标题").casefold()


def opportunity_identity_key(normalized_url: str, normalized_title: str) -> str:
    return sha256(
        f"{len(normalized_url)}:{normalized_url}{normalized_title}".encode()
    ).hexdigest()


def normalize_adapter_key(value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value.strip()):
        raise ValidationError("爬虫适配器不合法。")
    return value.strip()


def normalize_hostname(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("允许域名不合法。")
    hostname = value.strip().rstrip(".").casefold()
    if (
        not hostname
        or len(hostname) > 253
        or any(character in hostname for character in ("/", "\\", "@", ":", "\x00"))
    ):
        raise ValidationError("允许域名不合法。")
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValidationError("允许域名不合法。") from None
    labels = ascii_hostname.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in labels
    ):
        raise ValidationError("允许域名不合法。")
    return ascii_hostname


def normalize_opportunity_url(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValidationError("招聘地址不合法。")
    raw = value.strip()
    if (
        not raw
        or len(raw) > 2048
        or any(character in raw for character in ("\\", "\r", "\n", "\x00"))
    ):
        raise ValidationError("招聘地址不合法。")
    parsed = urlsplit(raw)
    try:
        port = parsed.port
    except ValueError:
        raise ValidationError("招聘地址不合法。") from None
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and port != 443)
    ):
        raise ValidationError("招聘地址必须使用无凭据的 HTTPS 地址。")
    hostname = normalize_hostname(parsed.hostname)
    netloc = hostname
    path = parsed.path or "/"
    normalized_path = posixpath.normpath(path)
    if path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    query_items = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_PARAMETERS
    ]
    normalized = urlunsplit(
        (
            "https",
            netloc,
            normalized_path,
            urlencode(query_items, doseq=True),
            parsed.fragment,
        )
    )
    return normalized, hostname


__all__ = [
    "normalize_adapter_key",
    "normalize_filter_label",
    "normalize_hostname",
    "normalize_opportunity_identity_title",
    "normalize_opportunity_url",
    "normalized_text",
    "opportunity_identity_key",
    "optional_text",
]
