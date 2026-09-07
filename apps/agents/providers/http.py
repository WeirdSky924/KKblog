from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from math import ceil
from urllib.parse import urljoin, urlsplit, urlunsplit

from apps.agents.contracts import MAX_REQUEST_TIMEOUT_SECONDS

MAX_PROVIDER_REQUEST_BYTES = 4 * 1024 * 1024
MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PROVIDER_REDIRECTS = 2
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ALLOWED_HEADERS = frozenset(
    {
        "accept",
        "anthropic-beta",
        "anthropic-version",
        "authorization",
        "content-type",
        "x-api-key",
    }
)
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_METADATA_ADDRESSES = frozenset(
    {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("100.100.100.200")}
)


class ProviderTransportError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ResolvedProviderTarget:
    url: str
    scheme: str
    hostname: str
    authority: str
    address: str
    port: int
    target: str


@dataclass(frozen=True, slots=True)
class ProviderHttpRequest:
    url: str
    hostname: str
    address: str
    port: int
    target: str
    connect_timeout_seconds: int
    read_timeout_seconds: int
    max_response_bytes: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Resolver = Callable[[str, int], Iterable[str]]
Transport = Callable[[ProviderHttpRequest], ProviderHttpResponse]


def _system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise ProviderTransportError(
            "agents.request_dns_failed.v1", retryable=True
        ) from None
    return tuple(dict.fromkeys(record[4][0] for record in records))


def _authority(hostname: str, port: int, scheme: str) -> str:
    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    return host if port == default_port else f"{host}:{port}"


def _parse_url(value: object) -> tuple[str, str, int, str, str]:
    if not isinstance(value, str) or not 1 <= len(value) <= 1000:
        raise ProviderTransportError("agents.endpoint_rejected.v1")
    if any(ord(character) < 32 for character in value):
        raise ProviderTransportError("agents.endpoint_rejected.v1")
    try:
        parsed = urlsplit(value.strip())
        parsed_port = parsed.port
        port = (
            parsed_port
            if parsed_port is not None
            else (443 if parsed.scheme == "https" else 80)
        )
    except ValueError:
        raise ProviderTransportError("agents.endpoint_rejected.v1") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65_535
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ProviderTransportError("agents.endpoint_rejected.v1")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        raise ProviderTransportError("agents.endpoint_rejected.v1") from None
    authority = _authority(hostname, port, parsed.scheme)
    path = parsed.path or "/"
    url = urlunsplit((parsed.scheme, authority, path, "", ""))
    return url, parsed.scheme, port, hostname, authority


def _normalize_allowlist(values: Iterable[str]) -> frozenset[str]:
    normalized = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid internal endpoint allowlist")
        try:
            parsed = urlsplit(f"//{value.strip()}")
            port = parsed.port
        except ValueError:
            raise ValueError("Invalid internal endpoint allowlist") from None
        if (
            not parsed.hostname
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid internal endpoint allowlist")
        try:
            host = parsed.hostname.encode("idna").decode("ascii").casefold()
        except UnicodeError:
            raise ValueError("Invalid internal endpoint allowlist") from None
        normalized.add(f"{host}:{port}")
    return frozenset(normalized)


def _address_kind(value: str) -> tuple[str, str]:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ProviderTransportError("agents.request_dns_failed.v1") from None
    if (
        address in _METADATA_ADDRESSES
        or address in _CGNAT
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        raise ProviderTransportError("agents.endpoint_address_denied.v1")
    if address.is_private or address.is_loopback:
        return address.compressed, "internal"
    if not address.is_global:
        raise ProviderTransportError("agents.endpoint_address_denied.v1")
    return address.compressed, "public"


class ProviderNetworkPolicy:
    def __init__(self, *, internal_allowlist: Iterable[str] = ()) -> None:
        self._internal_allowlist = _normalize_allowlist(internal_allowlist)

    def resolve(self, url: str, *, resolver: Resolver) -> ResolvedProviderTarget:
        normalized, scheme, port, hostname, authority = _parse_url(url)
        try:
            values = tuple(
                dict.fromkeys(str(item) for item in resolver(hostname, port))
            )
        except ProviderTransportError:
            raise
        except Exception:
            raise ProviderTransportError(
                "agents.request_dns_failed.v1", retryable=True
            ) from None
        if not values:
            raise ProviderTransportError("agents.request_dns_failed.v1", retryable=True)
        parsed = tuple(_address_kind(value) for value in values)
        kinds = {kind for _, kind in parsed}
        if len(kinds) != 1:
            raise ProviderTransportError("agents.endpoint_address_denied.v1")
        if "internal" in kinds:
            if f"{hostname}:{port}" not in self._internal_allowlist:
                raise ProviderTransportError("agents.endpoint_address_denied.v1")
        elif scheme != "https":
            raise ProviderTransportError("agents.endpoint_https_required.v1")
        target = urlunsplit(("", "", urlsplit(normalized).path or "/", "", ""))
        return ResolvedProviderTarget(
            url=normalized,
            scheme=scheme,
            hostname=hostname,
            authority=authority,
            address=parsed[0][0],
            port=port,
            target=target,
        )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, request: ProviderHttpRequest) -> None:
        super().__init__(
            request.hostname,
            request.port,
            timeout=request.connect_timeout_seconds,
        )
        self._request = request

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._request.address, self._request.port),
            timeout=self._request.connect_timeout_seconds,
        )
        self.sock.settimeout(self._request.read_timeout_seconds)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, request: ProviderHttpRequest) -> None:
        super().__init__(
            request.hostname,
            request.port,
            timeout=request.connect_timeout_seconds,
        )
        self._request = request

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._request.address, self._request.port),
            timeout=self._request.connect_timeout_seconds,
        )
        sock.settimeout(self._request.read_timeout_seconds)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _default_transport(request: ProviderHttpRequest) -> ProviderHttpResponse:
    connection_type = (
        _PinnedHTTPSConnection
        if urlsplit(request.url).scheme == "https"
        else _PinnedHTTPConnection
    )
    connection = connection_type(request)
    try:
        connection.request(
            "POST",
            request.target,
            body=request.body,
            headers={
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": _authority(
                    request.hostname, request.port, urlsplit(request.url).scheme
                ),
                "User-Agent": "KajSpace-AgentGateway/1.0",
                **request.headers,
            },
        )
        response = connection.getresponse()
        body = response.read(request.max_response_bytes + 1)
        headers = {name.casefold(): value for name, value in response.getheaders()}
        return ProviderHttpResponse(response.status, headers, body)
    except TimeoutError:
        raise ProviderTransportError(
            "agents.request_timeout.v1", retryable=True
        ) from None
    except (OSError, ssl.SSLError, http.client.HTTPException):
        raise ProviderTransportError(
            "agents.request_network_failed.v1", retryable=True
        ) from None
    finally:
        connection.close()


default_provider_transport = _default_transport
system_provider_resolver = _system_resolver


class SafeProviderHttpClient:
    def __init__(
        self,
        *,
        policy: ProviderNetworkPolicy,
        resolver: Resolver = _system_resolver,
        transport: Transport = _default_transport,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy
        self._resolver = resolver
        self._transport = transport
        self._monotonic = monotonic

    def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: int,
        max_response_bytes: int,
        max_redirects: int = 0,
    ) -> ProviderHttpResponse:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= MAX_REQUEST_TIMEOUT_SECONDS
            or isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= MAX_PROVIDER_RESPONSE_BYTES
            or not 0 <= max_redirects <= MAX_PROVIDER_REDIRECTS
        ):
            raise ValueError("Invalid provider request limits")
        safe_headers = self._headers(headers or {})
        try:
            body = json.dumps(
                dict(payload),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise ValueError("Invalid provider JSON payload") from None
        if len(body) > MAX_PROVIDER_REQUEST_BYTES:
            raise ProviderTransportError("agents.request_too_large.v1")

        deadline = self._monotonic() + timeout_seconds
        current = url
        original_authority = None
        for redirect_count in range(max_redirects + 1):
            resolved = self._policy.resolve(current, resolver=self._resolver)
            if original_authority is None:
                original_authority = resolved.authority
            elif resolved.authority != original_authority:
                raise ProviderTransportError("agents.redirect_authority_denied.v1")
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise ProviderTransportError(
                    "agents.request_timeout.v1", retryable=True
                )
            try:
                response = self._transport(
                    ProviderHttpRequest(
                        url=resolved.url,
                        hostname=resolved.hostname,
                        address=resolved.address,
                        port=resolved.port,
                        target=resolved.target,
                        connect_timeout_seconds=max(1, min(10, ceil(remaining))),
                        read_timeout_seconds=max(
                            1, min(MAX_REQUEST_TIMEOUT_SECONDS, ceil(remaining))
                        ),
                        max_response_bytes=max_response_bytes,
                        headers=safe_headers,
                        body=body,
                    )
                )
            except ProviderTransportError:
                raise
            except TimeoutError:
                raise ProviderTransportError(
                    "agents.request_timeout.v1", retryable=True
                ) from None
            except Exception:
                raise ProviderTransportError(
                    "agents.request_network_failed.v1", retryable=True
                ) from None
            if self._monotonic() > deadline:
                raise ProviderTransportError(
                    "agents.request_timeout.v1", retryable=True
                )
            if len(response.body) > max_response_bytes:
                raise ProviderTransportError("agents.response_too_large.v1")
            normalized_headers = {
                str(name).casefold(): str(value)
                for name, value in response.headers.items()
            }
            if response.status in _REDIRECT_STATUSES:
                location = normalized_headers.get("location", "").strip()
                if not location or redirect_count >= max_redirects:
                    raise ProviderTransportError("agents.redirect_invalid.v1")
                current = urljoin(resolved.url, location)
                continue
            return ProviderHttpResponse(
                status=response.status,
                headers=normalized_headers,
                body=bytes(response.body),
            )
        raise ProviderTransportError("agents.redirect_invalid.v1")

    @staticmethod
    def _headers(values: Mapping[str, str]) -> dict[str, str]:
        if len(values) > 8:
            raise ValueError("Invalid provider headers")
        result = {"Accept": "application/json", "Content-Type": "application/json"}
        for name, value in values.items():
            if (
                not isinstance(name, str)
                or name.casefold() not in _ALLOWED_HEADERS
                or not isinstance(value, str)
                or not 1 <= len(value) <= 8192
                or any(
                    ord(character) < 32 or ord(character) > 126 for character in value
                )
            ):
                raise ValueError("Invalid provider headers")
            result[name] = value
        return result


__all__ = [
    "MAX_PROVIDER_RESPONSE_BYTES",
    "ProviderHttpRequest",
    "ProviderHttpResponse",
    "ProviderNetworkPolicy",
    "ProviderTransportError",
    "ResolvedProviderTarget",
    "SafeProviderHttpClient",
    "default_provider_transport",
    "system_provider_resolver",
]
