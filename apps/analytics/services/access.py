from urllib.parse import unquote, urlsplit
from uuid import UUID

from apps.accounts.public import is_administrator

_DASHBOARD_ROOTS = (
    "/console",
    "/dashboard",
    "/login",
    "/logout",
    "/profile",
    "/reports",
    "/settings",
    "/share",
    "/sso",
    "/teams",
    "/websites",
)
_DASHBOARD_ENTRY = "/admin/analytics/umami"
_PUBLIC_ANALYTICS_PATHS = frozenset(
    {"/analytics/collect", "/analytics/script.js", "/api/send"}
)


def can_access_dashboard(account_id: UUID | str | None) -> bool:
    return is_administrator(account_id)


def is_dashboard_proxy_path(value: str) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 2_048:
        return False
    try:
        parsed = urlsplit(value)
        decoded_path = unquote(parsed.path, errors="strict")
    except (UnicodeError, ValueError):
        return False
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or decoded_path != parsed.path
        or "\\" in decoded_path
        or "//" in decoded_path
        or decoded_path in _PUBLIC_ANALYTICS_PATHS
        or decoded_path.startswith("/api/send/")
        or any(part in {".", ".."} for part in decoded_path.split("/"))
    ):
        return False
    if decoded_path == _DASHBOARD_ENTRY or decoded_path.startswith(
        f"{_DASHBOARD_ENTRY}/"
    ):
        return True
    if decoded_path == "/telemetry.js" or decoded_path.startswith("/_next/"):
        return True
    if decoded_path == "/api" or decoded_path.startswith("/api/"):
        return True
    return any(
        decoded_path == root or decoded_path.startswith(f"{root}/")
        for root in _DASHBOARD_ROOTS
    )
