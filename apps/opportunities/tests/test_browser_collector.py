import json
import os
import socket
import struct
import subprocess
import threading
from pathlib import Path

import pytest

from apps.opportunities.checks.browser import BrowserCollector
from apps.opportunities.checks.http import SafeRequestError


def _collector(tmp_path: Path, *, result=None, error=None) -> BrowserCollector:
    node = tmp_path / "node"
    chromium = tmp_path / "chromium"
    runner = tmp_path / "runner.cjs"
    node.write_text("", encoding="utf-8")
    chromium.write_text("", encoding="utf-8")
    runner.write_text("", encoding="utf-8")
    node.chmod(0o755)
    chromium.chmod(0o755)

    def execute(*args, **kwargs):
        del args, kwargs
        if error is not None:
            raise error
        return result

    return BrowserCollector(
        node_binary=node,
        chromium_binary=chromium,
        runner_path=runner,
        execute=execute,
        effective_uid=lambda: 10001,
    )


def _request(collector: BrowserCollector):
    return collector.collect(
        adapter_key="hikvision-v1",
        source_url="https://campushr.hikvision.com/school",
        allowed_hosts=frozenset({"campushr.hikvision.com"}),
        max_pages=10,
        max_opportunities=500,
        timeout_seconds=60,
    )


def test_browser_collector_accepts_bounded_versioned_json(tmp_path: Path) -> None:
    output = {
        "version": 1,
        "collector": "hikvision-v1",
        "complete": True,
        "pages_read": 2,
        "opportunities": [{"id": "job-1", "title": "算法工程师"}],
        "category_labels": ["算法"],
        "city_labels": ["杭州"],
        "cohort_labels": ["2026届"],
    }
    process = subprocess.CompletedProcess(
        args=(), returncode=0, stdout=json.dumps(output).encode(), stderr=b""
    )

    result = _request(_collector(tmp_path, result=process))

    assert result == output


def test_browser_collector_rejects_unknown_collectors(tmp_path: Path) -> None:
    collector = _collector(tmp_path)

    with pytest.raises(SafeRequestError) as error:
        collector.collect(
            adapter_key="administrator-script-v1",
            source_url="https://jobs.example.com/",
            allowed_hosts=frozenset({"jobs.example.com"}),
            max_pages=1,
            max_opportunities=1,
            timeout_seconds=10,
        )

    assert error.value.error_code == "opportunities.adapter_browser_denied.v1"


@pytest.mark.parametrize(
    ("process", "expected"),
    (
        (
            subprocess.CompletedProcess(args=(), returncode=1, stdout=b"", stderr=b""),
            "opportunities.adapter_browser_failed.v1",
        ),
        (
            subprocess.CompletedProcess(args=(), returncode=0, stdout=b"not-json"),
            "opportunities.adapter_browser_response_invalid.v1",
        ),
        (
            subprocess.CompletedProcess(
                args=(),
                returncode=0,
                stdout=json.dumps(
                    {
                        "version": 1,
                        "collector": "another-v1",
                        "complete": True,
                        "pages_read": 1,
                        "opportunities": [],
                        "category_labels": [],
                        "city_labels": [],
                        "cohort_labels": [],
                    }
                ).encode(),
            ),
            "opportunities.adapter_browser_response_invalid.v1",
        ),
    ),
)
def test_browser_collector_maps_invalid_subprocess_results(
    tmp_path: Path, process, expected
) -> None:
    with pytest.raises(SafeRequestError) as error:
        _request(_collector(tmp_path, result=process))

    assert error.value.error_code == expected


def test_browser_collector_maps_missing_runtime_and_timeout(tmp_path: Path) -> None:
    missing = BrowserCollector(
        node_binary=tmp_path / "missing-node",
        chromium_binary=tmp_path / "missing-chromium",
        runner_path=tmp_path / "missing-runner",
        effective_uid=lambda: 10001,
    )
    with pytest.raises(SafeRequestError) as unavailable:
        _request(missing)
    assert (
        unavailable.value.error_code == "opportunities.adapter_browser_unavailable.v1"
    )

    timed_out = _collector(
        tmp_path,
        error=subprocess.TimeoutExpired(cmd=("node",), timeout=60),
    )
    with pytest.raises(SafeRequestError) as timeout:
        _request(timed_out)
    assert timeout.value.error_code == "opportunities.collection_timeout.v1"


def test_browser_collector_preserves_safe_runner_error(tmp_path: Path) -> None:
    process = subprocess.CompletedProcess(
        args=(),
        returncode=2,
        stdout=json.dumps(
            {
                "version": 1,
                "collector": "hikvision-v1",
                "error_code": "opportunities.adapter_response_invalid.v1",
            }
        ).encode(),
        stderr=b"internal upstream details must not be surfaced",
    )

    with pytest.raises(SafeRequestError) as error:
        _request(_collector(tmp_path, result=process))

    assert error.value.error_code == "opportunities.adapter_response_invalid.v1"


def test_browser_collector_uses_authenticated_bounded_unix_service(tmp_path: Path):
    socket_path = tmp_path / "browser.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    socket_path.chmod(0o660)
    listener.listen(1)
    output = json.dumps(
        {
            "version": 1,
            "collector": "hikvision-v1",
            "complete": True,
            "pages_read": 1,
            "opportunities": [],
            "category_labels": [],
            "city_labels": [],
            "cohort_labels": [],
        }
    ).encode()

    def serve():
        with listener:
            connection, _ = listener.accept()
            with connection:
                request_size = struct.unpack("!I", connection.recv(4))[0]
                request = connection.recv(request_size)
                assert json.loads(request)["collector"] == "hikvision-v1"
                connection.sendall(struct.pack("!II", 0, len(output)) + output)

    service = threading.Thread(target=serve)
    service.start()
    collector = BrowserCollector(
        socket_path=socket_path,
        browser_service_uid=os.geteuid(),
        execute=lambda *args, **kwargs: pytest.fail(
            "local browser runner must not execute"
        ),
    )

    result = _request(collector)

    service.join(timeout=5)
    assert not service.is_alive()
    assert result["complete"] is True
    assert result["opportunities"] == []


def test_browser_collector_rejects_an_untrusted_unix_service(tmp_path: Path):
    socket_path = tmp_path / "browser.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        socket_path.chmod(0o660)
        listener.listen(1)
        collector = BrowserCollector(
            socket_path=socket_path,
            browser_service_uid=os.geteuid() + 1,
        )

        with pytest.raises(SafeRequestError) as error:
            _request(collector)

    assert error.value.error_code == "opportunities.adapter_browser_unavailable.v1"
