from __future__ import annotations

import json
import os
import re
import socket
import stat
import struct
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from urllib.parse import urlsplit

from ..validators import normalize_hostname, normalize_opportunity_url
from .http import SafeRequestError

_PROTOCOL_VERSION = 1
_COLLECTORS = frozenset(
    {
        "alibaba-campus-v1",
        "bytedance-campus-v1",
        "feishu-career-v1",
        "hikvision-v1",
        "xiaomi-campus-v1",
        "xiaomi-intern-v1",
    }
)
_RESULT_KEYS = frozenset(
    {
        "version",
        "collector",
        "complete",
        "pages_read",
        "opportunities",
        "category_labels",
        "city_labels",
        "cohort_labels",
        "error_code",
    }
)
_SAFE_ERROR = re.compile(r"opportunities\.[a-z0-9_.-]{1,80}\.v1\Z")
_MAX_STDOUT_BYTES = 8 * 1024 * 1024
_REQUEST_HEADER = struct.Struct("!I")
_RESPONSE_HEADER = struct.Struct("!II")


class BrowserCollector:
    def __init__(
        self,
        *,
        node_binary: str | Path | None = None,
        chromium_binary: str | Path | None = None,
        runner_path: str | Path | None = None,
        socket_path: str | Path | None = None,
        browser_service_uid: int | None = None,
        execute: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        effective_uid: Callable[[], int] = os.geteuid,
    ) -> None:
        self._node_binary = Path(
            node_binary
            or os.environ.get(
                "KAJ_OPPORTUNITY_NODE_BINARY",
                "/usr/local/bin/node",
            )
        )
        default_chromium = (
            "/usr/bin/chromium"
            if Path("/usr/bin/chromium").is_file()
            else "/usr/bin/google-chrome"
        )
        self._chromium_binary = Path(
            chromium_binary
            or os.environ.get(
                "KAJ_OPPORTUNITY_CHROMIUM_BINARY",
                default_chromium,
            )
        )
        self._runner_path = Path(
            runner_path or Path(__file__).with_name("browser_runner.cjs")
        )
        configured_socket = socket_path or os.environ.get(
            "KAJ_OPPORTUNITY_BROWSER_SOCKET", ""
        )
        self._socket_path = Path(configured_socket) if configured_socket else None
        configured_uid = (
            browser_service_uid
            if browser_service_uid is not None
            else os.environ.get("KAJ_OPPORTUNITY_BROWSER_UID", "999")
        )
        try:
            self._browser_service_uid = int(configured_uid)
        except (TypeError, ValueError):
            self._browser_service_uid = -1
        self._execute = execute
        self._effective_uid = effective_uid

    @staticmethod
    def _hosts(values: Iterable[str]) -> tuple[str, ...]:
        try:
            hosts = tuple(sorted({normalize_hostname(value) for value in values}))
        except Exception:
            raise SafeRequestError("opportunities.adapter_browser_denied.v1") from None
        if not hosts or len(hosts) > 12:
            raise SafeRequestError("opportunities.adapter_browser_denied.v1")
        return hosts

    @staticmethod
    def _limit(value: int, *, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        if not minimum <= value <= maximum:
            raise SafeRequestError("opportunities.adapter_config_invalid.v1")
        return value

    def _command(self) -> tuple[str, ...]:
        if (
            not self._node_binary.is_file()
            or not os.access(self._node_binary, os.X_OK)
            or not self._chromium_binary.is_file()
            or not os.access(self._chromium_binary, os.X_OK)
        ):
            raise SafeRequestError("opportunities.adapter_browser_unavailable.v1")
        if not self._runner_path.is_file():
            raise SafeRequestError("opportunities.adapter_browser_unavailable.v1")
        command = (str(self._node_binary), str(self._runner_path))
        if self._effective_uid() == 0:
            setpriv = Path("/usr/bin/setpriv")
            if not setpriv.is_file():
                raise SafeRequestError("opportunities.adapter_browser_unavailable.v1")
            command = (
                str(setpriv),
                "--reuid=999",
                "--regid=988",
                "--clear-groups",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                *command,
            )
        return command

    @staticmethod
    def _receive(stream: socket.socket, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining:
            chunk = stream.recv(remaining)
            if not chunk:
                raise OSError("browser service response ended early")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _socket_process(self, request: bytes, *, timeout: int):
        path = self._socket_path
        if path is None or not path.is_absolute() or self._browser_service_uid < 0:
            raise SafeRequestError("opportunities.adapter_browser_unavailable.v1")
        try:
            metadata = path.stat()
        except OSError:
            raise SafeRequestError(
                "opportunities.adapter_browser_unavailable.v1"
            ) from None
        if (
            not stat.S_ISSOCK(metadata.st_mode)
            or metadata.st_mode & 0o002
            or len(request) > 16_384
        ):
            raise SafeRequestError("opportunities.adapter_browser_unavailable.v1")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(timeout + 5)
                stream.connect(str(path))
                if hasattr(socket, "SO_PEERCRED"):
                    credentials = stream.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                    )
                    _, peer_uid, _ = struct.unpack("3i", credentials)
                    if peer_uid != self._browser_service_uid:
                        raise OSError("browser service peer is not trusted")
                stream.sendall(_REQUEST_HEADER.pack(len(request)) + request)
                stream.shutdown(socket.SHUT_WR)
                header = self._receive(stream, _RESPONSE_HEADER.size)
                return_code, output_size = _RESPONSE_HEADER.unpack(header)
                if (
                    return_code not in (0, 2)
                    or not 1 <= output_size <= _MAX_STDOUT_BYTES
                ):
                    raise OSError("browser service response header is invalid")
                output = self._receive(stream, output_size)
        except TimeoutError:
            raise SafeRequestError("opportunities.collection_timeout.v1") from None
        except OSError:
            raise SafeRequestError(
                "opportunities.adapter_browser_unavailable.v1"
            ) from None
        return subprocess.CompletedProcess(
            args=(str(path),), returncode=return_code, stdout=output, stderr=b""
        )

    @staticmethod
    def _decode(process, *, collector: str, max_opportunities: int) -> dict:
        output = process.stdout if isinstance(process.stdout, bytes) else b""
        if len(output) > _MAX_STDOUT_BYTES:
            raise SafeRequestError(
                "opportunities.adapter_browser_response_too_large.v1"
            )
        try:
            result = json.loads(output.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if process.returncode:
                raise SafeRequestError(
                    "opportunities.adapter_browser_failed.v1"
                ) from None
            raise SafeRequestError(
                "opportunities.adapter_browser_response_invalid.v1"
            ) from None
        if not isinstance(result, dict) or not set(result).issubset(_RESULT_KEYS):
            raise SafeRequestError("opportunities.adapter_browser_response_invalid.v1")
        if (
            result.get("version") != _PROTOCOL_VERSION
            or result.get("collector") != collector
        ):
            raise SafeRequestError("opportunities.adapter_browser_response_invalid.v1")
        if process.returncode:
            error_code = result.get("error_code")
            if isinstance(error_code, str) and _SAFE_ERROR.fullmatch(error_code):
                raise SafeRequestError(error_code)
            raise SafeRequestError("opportunities.adapter_browser_failed.v1")
        opportunities = result.get("opportunities")
        pages_read = result.get("pages_read")
        labels = (
            result.get("category_labels"),
            result.get("city_labels"),
            result.get("cohort_labels"),
        )
        if (
            not isinstance(result.get("complete"), bool)
            or isinstance(pages_read, bool)
            or not isinstance(pages_read, int)
            or pages_read < 1
            or not isinstance(opportunities, list)
            or len(opportunities) > max_opportunities
            or any(not isinstance(item, dict) for item in opportunities)
            or any(
                not isinstance(group, list)
                or len(group) > max_opportunities
                or any(not isinstance(label, str) for label in group)
                for group in labels
            )
        ):
            raise SafeRequestError("opportunities.adapter_browser_response_invalid.v1")
        return result

    def collect(
        self,
        *,
        adapter_key: str,
        source_url: str,
        allowed_hosts: Iterable[str],
        max_pages: int,
        max_opportunities: int,
        timeout_seconds: int,
    ) -> Mapping[str, object]:
        if adapter_key not in _COLLECTORS:
            raise SafeRequestError("opportunities.adapter_browser_denied.v1")
        hosts = self._hosts(allowed_hosts)
        try:
            normalized_url, source_host = normalize_opportunity_url(source_url)
        except Exception:
            raise SafeRequestError("opportunities.adapter_browser_denied.v1") from None
        if source_host not in hosts or urlsplit(normalized_url).scheme != "https":
            raise SafeRequestError("opportunities.adapter_browser_denied.v1")
        page_limit = self._limit(max_pages, minimum=1, maximum=100)
        item_limit = self._limit(max_opportunities, minimum=1, maximum=5000)
        duration = self._limit(timeout_seconds, minimum=1, maximum=600)
        request = json.dumps(
            {
                "version": _PROTOCOL_VERSION,
                "collector": adapter_key,
                "source_url": normalized_url,
                "allowed_hosts": hosts,
                "max_pages": page_limit,
                "max_opportunities": item_limit,
                "timeout_ms": duration * 1000,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if self._socket_path is not None:
            process = self._socket_process(request, timeout=duration)
        else:
            environment = {
                "HOME": (
                    "/var/lib/blog-browser" if self._effective_uid() == 0 else "/tmp"
                ),
                "PATH": (
                    "/opt/node-v22.23.1-linux-x64/bin:/usr/local/bin:/usr/bin:/bin"
                ),
                "LANG": "C.UTF-8",
                "NODE_PATH": str(Path.cwd() / "node_modules"),
                "KAJ_OPPORTUNITY_CHROMIUM_BINARY": str(self._chromium_binary),
            }
            try:
                process = self._execute(
                    self._command(),
                    input=request,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=duration + 5,
                    check=False,
                    env=environment,
                    cwd=Path.cwd(),
                )
            except subprocess.TimeoutExpired:
                raise SafeRequestError("opportunities.collection_timeout.v1") from None
            except (OSError, ValueError):
                raise SafeRequestError(
                    "opportunities.adapter_browser_unavailable.v1"
                ) from None
        return self._decode(
            process,
            collector=adapter_key,
            max_opportunities=item_limit,
        )


__all__ = ["BrowserCollector"]
