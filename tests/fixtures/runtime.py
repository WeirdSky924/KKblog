import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from urllib.request import Request, urlopen

import pytest
from django.conf import settings
from django.test import override_settings
from redis import Redis

from apps.core.ids import new_ulid


class MailpitClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def request(self, path: str, *, method: str = "GET") -> object:
        request = Request(f"{self.api_url}{path}", method=method)
        with urlopen(request, timeout=5) as response:
            body = response.read()
            content_type = response.headers.get_content_type()
        if not body:
            return None
        if content_type == "application/json":
            return json.loads(body)
        return body.decode("utf-8")

    def clear(self) -> None:
        self.request("/api/v1/messages", method="DELETE")

    def messages(self) -> list[dict[str, object]]:
        result = self.request("/api/v1/messages")
        if not isinstance(result, dict) or not isinstance(result.get("messages"), list):
            raise AssertionError("Mailpit returned an invalid messages response")
        return result["messages"]


@pytest.fixture
def isolated_media_root(tmp_path: Path) -> Iterator[Path]:
    media_root = tmp_path / "media"
    media_root.mkdir(mode=0o700)
    project_var = Path(settings.BASE_DIR) / "var"
    assert not media_root.is_relative_to(project_var)
    with override_settings(MEDIA_ROOT=media_root):
        try:
            yield media_root
        finally:
            shutil.rmtree(media_root)


@pytest.fixture
def isolated_redis() -> Iterator[tuple[Redis, str]]:
    redis_url = getattr(settings, "TEST_REDIS_URL", None)
    if not redis_url:
        pytest.fail("KAJ_TEST_REDIS_URL is required for integration tests")
    client = Redis.from_url(redis_url, decode_responses=False, socket_timeout=2)
    client.ping()
    prefix = f"kaj:test:{new_ulid().lower()}:"
    try:
        yield client, prefix
    finally:
        keys = list(client.scan_iter(match=f"{prefix}*", count=100))
        if keys:
            client.delete(*keys)
        client.close()


@pytest.fixture
def mailpit() -> Iterator[MailpitClient]:
    api_url = getattr(settings, "MAILPIT_API_URL", None)
    if not api_url:
        pytest.fail(
            "KAJ_TEST_MAILPIT_SMTP_URL and KAJ_TEST_MAILPIT_API_URL are required"
        )
    client = MailpitClient(api_url)
    client.clear()
    try:
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
        ):
            yield client
    finally:
        client.clear()


@pytest.fixture(scope="session")
def isolated_runtime_environment() -> dict[str, str]:
    required = (
        "KAJ_TEST_DATABASE_URL",
        "KAJ_TEST_REDIS_URL",
        "KAJ_TEST_MAILPIT_SMTP_URL",
        "KAJ_TEST_MAILPIT_API_URL",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        pytest.fail("Missing isolated test environment keys: " + ", ".join(missing))
    return {name: "configured" for name in required}
