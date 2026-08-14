import json
import os
import socket
import struct
from pathlib import Path
from types import SimpleNamespace

from apps.opportunities.checks import browser_service


def _options(tmp_path: Path):
    return SimpleNamespace(
        peer_uid=os.geteuid(),
        node=tmp_path / "node",
        runner=tmp_path / "runner.cjs",
        chrome=tmp_path / "chrome",
        home=tmp_path,
        workdir=tmp_path,
    )


def _request():
    return json.dumps(
        {
            "version": 1,
            "collector": "hikvision-v1",
            "source_url": "https://campushr.hikvision.com/school",
            "allowed_hosts": ["campushr.hikvision.com"],
            "max_pages": 1,
            "max_opportunities": 10,
            "timeout_ms": 10_000,
        },
        separators=(",", ":"),
    ).encode()


def _response(stream):
    header = stream.recv(8)
    return_code, size = struct.unpack("!II", header)
    return return_code, json.loads(stream.recv(size))


def test_browser_service_forwards_one_bounded_request(monkeypatch, tmp_path):
    expected = {
        "version": 1,
        "collector": "hikvision-v1",
        "complete": True,
        "pages_read": 1,
        "opportunities": [],
        "category_labels": [],
        "city_labels": [],
        "cohort_labels": [],
    }
    observed = {}

    def run(command, request, **kwargs):
        observed.update(command=command, request=json.loads(request), kwargs=kwargs)
        return 0, json.dumps(expected).encode()

    monkeypatch.setattr(browser_service, "_run", run)
    client, server = socket.socketpair()
    request = _request()
    with client, server:
        client.sendall(struct.pack("!I", len(request)) + request)
        client.shutdown(socket.SHUT_WR)

        browser_service._handle(server, options=_options(tmp_path))

        return_code, response = _response(client)
    assert return_code == 0
    assert response == expected
    assert observed["request"]["collector"] == "hikvision-v1"
    assert observed["kwargs"]["timeout"] == 15


def test_browser_service_returns_only_a_safe_error_for_invalid_runner_output(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        browser_service,
        "_run",
        lambda *args, **kwargs: (1, b"private upstream failure details"),
    )
    client, server = socket.socketpair()
    request = _request()
    with client, server:
        client.sendall(struct.pack("!I", len(request)) + request)
        client.shutdown(socket.SHUT_WR)

        browser_service._handle(server, options=_options(tmp_path))

        return_code, response = _response(client)
    assert return_code == 2
    assert response == {
        "version": 1,
        "collector": "hikvision-v1",
        "error_code": "opportunities.adapter_browser_failed.v1",
    }
    assert "private" not in json.dumps(response)
