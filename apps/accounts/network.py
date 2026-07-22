import hashlib
import hmac
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from django.conf import settings
from django.http import HttpRequest


class ClientIpError(ValueError):
    pass


def normalize_ip(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ClientIpError("Invalid client address")
    if "," in value or len(value) > 64:
        raise ClientIpError("Invalid client address")
    try:
        parsed: IPv4Address | IPv6Address = ip_address(value)
    except ValueError:
        raise ClientIpError("Invalid client address") from None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        return str(parsed.ipv4_mapped)
    return str(parsed)


def _trusted_peer(address: str, cidrs: Iterable[str]) -> bool:
    parsed = ip_address(address)
    for value in cidrs:
        try:
            network = ip_network(value, strict=False)
        except ValueError:
            raise ClientIpError("Invalid trusted proxy configuration") from None
        if parsed.version == network.version and parsed in network:
            return True
    return False


def resolve_client_ip(
    request: HttpRequest,
    *,
    trusted_proxy_cidrs: Iterable[str] | None = None,
) -> str:
    peer = normalize_ip(request.META.get("REMOTE_ADDR", ""))
    trusted = tuple(
        trusted_proxy_cidrs
        if trusted_proxy_cidrs is not None
        else getattr(settings, "TRUSTED_PROXY_CIDRS", ())
    )
    if not _trusted_peer(peer, trusted):
        return peer
    forwarded = request.META.get("HTTP_X_KAJ_CLIENT_IP", "")
    if not forwarded:
        raise ClientIpError("Trusted proxy omitted client address")
    return normalize_ip(forwarded)


def network_subject_digest(address: str) -> str:
    normalized = normalize_ip(address)
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"network:{normalized}".encode(),
        hashlib.sha256,
    ).hexdigest()
