from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import stat
import struct
import subprocess
from pathlib import Path

_REQUEST_HEADER = struct.Struct("!I")
_RESPONSE_HEADER = struct.Struct("!II")
_MAX_REQUEST_BYTES = 16_384
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_COLLECTOR = re.compile(r"[a-z][a-z0-9-]{1,79}\Z")
_stopping = False


class ServiceRequestError(ValueError):
    pass


def _receive(stream: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise ServiceRequestError("request ended early")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _request(stream: socket.socket) -> tuple[bytes, str, float]:
    header = _receive(stream, _REQUEST_HEADER.size)
    request_size = _REQUEST_HEADER.unpack(header)[0]
    if not 2 <= request_size <= _MAX_REQUEST_BYTES:
        raise ServiceRequestError("request size is invalid")
    raw = _receive(stream, request_size)
    if stream.recv(1):
        raise ServiceRequestError("request has trailing data")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceRequestError("request JSON is invalid") from None
    collector = payload.get("collector") if isinstance(payload, dict) else None
    timeout_ms = payload.get("timeout_ms") if isinstance(payload, dict) else None
    if (
        not isinstance(collector, str)
        or not _COLLECTOR.fullmatch(collector)
        or isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or not 1_000 <= timeout_ms <= 600_000
    ):
        raise ServiceRequestError("request bounds are invalid")
    return raw, collector, timeout_ms / 1000 + 5


def _safe_failure(collector: str) -> bytes:
    safe_collector = collector if _COLLECTOR.fullmatch(collector) else "invalid"
    return json.dumps(
        {
            "version": 1,
            "collector": safe_collector,
            "error_code": "opportunities.adapter_browser_failed.v1",
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _run(command: tuple[str, str], request: bytes, *, timeout: float, environment, cwd):
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        cwd=cwd,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(input=request, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    return process.returncode, output


def _handle(stream: socket.socket, *, options) -> None:
    collector = "invalid"
    try:
        if hasattr(socket, "SO_PEERCRED"):
            credentials = stream.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            _, peer_uid, _ = struct.unpack("3i", credentials)
            if peer_uid != options.peer_uid:
                raise ServiceRequestError("peer UID is not allowed")
        request, collector, timeout = _request(stream)
        return_code, output = _run(
            (str(options.node), str(options.runner)),
            request,
            timeout=timeout,
            environment={
                "HOME": str(options.home),
                "LANG": "C.UTF-8",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "NODE_PATH": str(options.workdir / "node_modules"),
                "KAJ_OPPORTUNITY_CHROMIUM_BINARY": str(options.chrome),
            },
            cwd=options.workdir,
        )
        if return_code not in (0, 2) or not 1 <= len(output) <= _MAX_RESPONSE_BYTES:
            return_code = 2
            output = _safe_failure(collector)
    except (OSError, ServiceRequestError, subprocess.TimeoutExpired):
        return_code = 2
        output = _safe_failure(collector)
    try:
        stream.sendall(_RESPONSE_HEADER.pack(return_code, len(output)) + output)
    except OSError:
        pass


def _path(value: str, *, executable: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise argparse.ArgumentTypeError("path must be an existing absolute file")
    if executable and not os.access(path, os.X_OK):
        raise argparse.ArgumentTypeError("path must be executable")
    return path


def _directory(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise argparse.ArgumentTypeError("path must be an existing absolute directory")
    return path


def _arguments():
    parser = argparse.ArgumentParser(description="Serve the opportunity browser runner")
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--socket-gid", required=True, type=int)
    parser.add_argument("--peer-uid", required=True, type=int)
    parser.add_argument(
        "--node", required=True, type=lambda value: _path(value, executable=True)
    )
    parser.add_argument(
        "--chrome", required=True, type=lambda value: _path(value, executable=True)
    )
    parser.add_argument("--runner", required=True, type=_path)
    parser.add_argument("--workdir", required=True, type=_directory)
    parser.add_argument("--home", required=True, type=_directory)
    return parser.parse_args()


def _stop(signum, frame) -> None:
    del signum, frame
    global _stopping
    _stopping = True


def main() -> None:
    options = _arguments()
    if (
        not options.socket.is_absolute()
        or options.socket.parent.is_symlink()
        or not options.socket.parent.is_dir()
        or options.peer_uid < 1
        or options.socket_gid < 1
    ):
        raise SystemExit("unsafe browser service configuration")
    if options.socket.exists() or options.socket.is_symlink():
        metadata = options.socket.lstat()
        if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise SystemExit("unsafe existing browser service socket")
        options.socket.unlink()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(options.socket))
        os.chown(options.socket, -1, options.socket_gid)
        os.chmod(options.socket, 0o660)
        listener.listen(8)
        listener.settimeout(1)
        try:
            while not _stopping:
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    connection.settimeout(5)
                    _handle(connection, options=options)
        finally:
            try:
                options.socket.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
