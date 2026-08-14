from __future__ import annotations

import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from math import ceil
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..validators import normalize_hostname, normalize_opportunity_url

DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 65_536
MAX_ADAPTER_RESPONSE_BYTES = 262_144
MAX_LARGE_ADAPTER_RESPONSE_BYTES = 393_216
DEFAULT_MAX_REDIRECTS = 5
MIN_REQUEST_INTERVAL_SECONDS = 2
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ADAPTER_REQUEST_HEADERS = frozenset(
    {"origin", "referer", "x-hw-id", "x-jalor-tenantalias", "x-referer"}
)
_TITLE = re.compile(rb"<title(?:\s[^>]*)?>(.*?)</title\s*>", re.I | re.S)
_SPACE = re.compile(r"\s+")


class SafeRequestError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True, slots=True)
class TransportRequest:
    url: str
    hostname: str
    address: str
    target: str
    timeout_seconds: int
    max_response_bytes: int
    method: str = "GET"
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class SafeHttpResult:
    status: int
    final_url: str
    title: str
    body: bytes
    truncated: bool


Resolver = Callable[[str], Iterable[str]]
Transport = Callable[[TransportRequest], TransportResponse]
RequestGuard = Callable[[str], None]


class DomainRateLimiter:
    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._next_allowed_at: dict[str, float] = {}

    def wait(self, hostname: str, *, interval_seconds: int) -> None:
        now = self._monotonic()
        remaining = self._next_allowed_at.get(hostname, now) - now
        if remaining > 0:
            self._sleeper(remaining)
            now = self._monotonic()
        self._next_allowed_at[hostname] = now + interval_seconds


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, address: str, *, timeout: int) -> None:
        super().__init__(hostname, port=443, timeout=timeout)
        self._pinned_address = address

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._pinned_address, 443),
            timeout=self.timeout,
        )
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _system_resolver(hostname: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(
            hostname,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise SafeRequestError("opportunities.request_dns_failed.v1") from None
    return tuple(dict.fromkeys(record[4][0] for record in records))


def _default_transport(request: TransportRequest) -> TransportResponse:
    connection = _PinnedHTTPSConnection(
        request.hostname,
        request.address,
        timeout=request.timeout_seconds,
    )
    try:
        connection.request(
            request.method,
            request.target,
            body=request.body or None,
            headers={
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": request.hostname,
                "User-Agent": "KajSpace-OpportunityChecker/1.0",
                **request.headers,
            },
        )
        response = connection.getresponse()
        body = response.read(request.max_response_bytes + 1)
        headers = {key.casefold(): value for key, value in response.getheaders()}
        return TransportResponse(response.status, headers, body)
    except TimeoutError:
        raise SafeRequestError("opportunities.request_timeout.v1") from None
    except (OSError, ssl.SSLError, http.client.HTTPException):
        raise SafeRequestError("opportunities.request_network_failed.v1") from None
    finally:
        connection.close()


def _validated_addresses(resolver: Resolver, hostname: str) -> tuple[str, ...]:
    try:
        values = tuple(dict.fromkeys(str(value) for value in resolver(hostname)))
    except SafeRequestError:
        raise
    except Exception:
        raise SafeRequestError("opportunities.request_dns_failed.v1") from None
    if not values:
        raise SafeRequestError("opportunities.request_dns_failed.v1")
    parsed = []
    for value in values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise SafeRequestError("opportunities.request_dns_failed.v1") from None
        if not address.is_global:
            raise SafeRequestError("opportunities.request_address_denied.v1")
        parsed.append(address.compressed)
    return tuple(parsed)


def _request_target(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(("", "", parsed.path or "/", parsed.query, ""))


def _page_title(body: bytes) -> str:
    match = _TITLE.search(body)
    if match is None:
        return ""
    decoded = match.group(1).decode("utf-8", errors="replace")
    title = _SPACE.sub(" ", html.unescape(decoded)).strip()
    return title[:300]


def _response_body(response: TransportResponse, *, maximum: int) -> tuple[bytes, bool]:
    encoding = response.headers.get("content-encoding", "").casefold().strip()
    if encoding in ("", "identity"):
        return bytes(response.body[:maximum]), len(response.body) > maximum
    if encoding != "gzip":
        raise SafeRequestError("opportunities.request_encoding_unsupported.v1")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoded = decoder.decompress(response.body, maximum + 1)
        truncated = len(decoded) > maximum or not decoder.eof
    except zlib.error:
        raise SafeRequestError("opportunities.request_encoding_invalid.v1") from None
    return bytes(decoded[:maximum]), truncated


class SafeHttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: Iterable[str],
        resolver: Resolver = _system_resolver,
        transport: Transport = _default_transport,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        request_interval_seconds: int = MIN_REQUEST_INTERVAL_SECONDS,
        rate_limiter: DomainRateLimiter | None = None,
    ) -> None:
        try:
            self._allowed_hosts = frozenset(
                normalize_hostname(host) for host in allowed_hosts
            )
        except Exception:
            raise ValueError("Invalid allowed hosts") from None
        if not self._allowed_hosts:
            raise ValueError("At least one allowed host is required")
        if (
            isinstance(request_interval_seconds, bool)
            or not isinstance(request_interval_seconds, int)
            or request_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS
        ):
            raise ValueError("Invalid request interval")
        self._resolver = resolver
        self._transport = transport
        self._monotonic = monotonic
        self._request_interval = request_interval_seconds
        self._rate_limiter = rate_limiter or DomainRateLimiter(
            monotonic=monotonic,
            sleeper=sleeper,
        )

    def _validated_url(self, value: str) -> tuple[str, str]:
        try:
            normalized, hostname = normalize_opportunity_url(value)
        except Exception:
            raise SafeRequestError("opportunities.request_https_required.v1") from None
        if hostname not in self._allowed_hosts:
            raise SafeRequestError("opportunities.request_host_denied.v1")
        return normalized, hostname

    def _rate_limit(self, hostname: str) -> None:
        self._rate_limiter.wait(
            hostname,
            interval_seconds=self._request_interval,
        )

    def _request(
        self,
        url: str,
        *,
        method: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_redirects: int = 0,
        request_guard: RequestGuard | None = None,
    ) -> SafeHttpResult:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= DEFAULT_TIMEOUT_SECONDS
            or isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= MAX_LARGE_ADAPTER_RESPONSE_BYTES
            or isinstance(max_redirects, bool)
            or not isinstance(max_redirects, int)
            or not 0 <= max_redirects <= DEFAULT_MAX_REDIRECTS
            or (request_guard is not None and not callable(request_guard))
        ):
            raise ValueError("Invalid safe request limit")

        current, hostname = self._validated_url(url)
        deadline = self._monotonic() + timeout_seconds
        for redirect_count in range(max_redirects + 1):
            if request_guard is not None:
                request_guard(current)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise SafeRequestError("opportunities.request_timeout.v1")
            addresses = _validated_addresses(self._resolver, hostname)
            self._rate_limit(hostname)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise SafeRequestError("opportunities.request_timeout.v1")
            try:
                response = self._transport(
                    TransportRequest(
                        url=current,
                        hostname=hostname,
                        address=addresses[0],
                        target=_request_target(current),
                        method=method,
                        headers=headers,
                        body=body,
                        timeout_seconds=max(1, ceil(remaining)),
                        max_response_bytes=max_response_bytes,
                    )
                )
            except SafeRequestError:
                raise
            except TimeoutError:
                raise SafeRequestError("opportunities.request_timeout.v1") from None
            except Exception:
                raise SafeRequestError(
                    "opportunities.request_network_failed.v1"
                ) from None
            if response.status in _REDIRECT_STATUSES:
                location = response.headers.get("location") or response.headers.get(
                    "Location"
                )
                if not isinstance(location, str) or not location.strip():
                    raise SafeRequestError("opportunities.request_redirect_invalid.v1")
                if redirect_count >= max_redirects:
                    raise SafeRequestError("opportunities.request_redirect_limit.v1")
                current, hostname = self._validated_url(urljoin(current, location))
                continue
            body, truncated = _response_body(response, maximum=max_response_bytes)
            return SafeHttpResult(
                status=response.status,
                final_url=current,
                title=_page_title(body),
                body=body,
                truncated=truncated,
            )
        raise SafeRequestError("opportunities.request_redirect_limit.v1")

    def get(
        self,
        url: str,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        request_guard: RequestGuard | None = None,
    ) -> SafeHttpResult:
        return self._request(
            url,
            method="GET",
            headers={},
            body=b"",
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_redirects=max_redirects,
            request_guard=request_guard,
        )

    def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_redirects: int = 0,
        request_guard: RequestGuard | None = None,
    ) -> SafeHttpResult:
        if not isinstance(payload, Mapping):
            raise ValueError("Invalid JSON request payload")
        adapter_headers: dict[str, str] = {}
        if headers is not None:
            if not isinstance(headers, Mapping) or len(headers) > 8:
                raise ValueError("Invalid adapter request headers")
            for name, value in headers.items():
                if (
                    not isinstance(name, str)
                    or name.casefold() not in _ADAPTER_REQUEST_HEADERS
                    or not isinstance(value, str)
                    or not value
                    or len(value) > 512
                    or any(
                        ord(character) < 32 or ord(character) > 126
                        for character in value
                    )
                ):
                    raise ValueError("Invalid adapter request headers")
                adapter_headers[name] = value
        try:
            body = json.dumps(
                dict(payload),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise ValueError("Invalid JSON request payload") from None
        if len(body) > 16_384:
            raise ValueError("JSON request payload is too large")
        return self._request(
            url,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "LangType": "zh_CN",
                "X-Requested-With": "XMLHttpRequest",
                "X-PaaS-DeviceType": "PC",
                **adapter_headers,
            },
            body=body,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_redirects=max_redirects,
            request_guard=request_guard,
        )


__all__ = [
    "MAX_ADAPTER_RESPONSE_BYTES",
    "MAX_LARGE_ADAPTER_RESPONSE_BYTES",
    "SafeHttpClient",
    "SafeHttpResult",
    "SafeRequestError",
    "TransportRequest",
    "TransportResponse",
    "DomainRateLimiter",
]
