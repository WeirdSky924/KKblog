import time
from pathlib import Path

import pytest
from django.conf import settings
from django.core.mail import send_mail
from django.db import connection

from apps.core.ids import new_ulid


@pytest.mark.django_db(transaction=True)
def test_postgresql_is_real_isolated_and_utc(isolated_runtime_environment) -> None:
    del isolated_runtime_environment
    config = settings.DATABASES["default"]
    assert connection.vendor == "postgresql"
    assert config["HOST"] in {"127.0.0.1", "localhost", "::1"}
    assert str(config["NAME"]).startswith("test_kaj_test_")
    assert config["USER"] == "kaj_test_runner"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('server_version'), "
            "current_setting('TimeZone'), current_database(), current_user"
        )
        version, timezone, database_name, username = cursor.fetchone()
    assert int(version.split(".", 1)[0]) >= 16
    assert timezone == "UTC"
    assert database_name.startswith("test_kaj_test_")
    assert username == "kaj_test_runner"


def test_redis_round_trip_ttl_and_cleanup(
    isolated_runtime_environment,
    isolated_redis,
) -> None:
    del isolated_runtime_environment
    client, prefix = isolated_redis
    key = f"{prefix}round-trip"
    assert client.set(key, b"redis-readback", ex=30, nx=True)
    assert client.get(key) == b"redis-readback"
    assert 1 <= client.ttl(key) <= 30
    assert client.delete(key) == 1
    assert client.get(key) is None


def test_media_round_trip_uses_temporary_directory(
    isolated_runtime_environment,
    isolated_media_root: Path,
) -> None:
    del isolated_runtime_environment
    payload = b"kaj-media-readback"
    target = isolated_media_root / "probe.bin"
    target.write_bytes(payload)
    assert target.read_bytes() == payload
    assert target.stat().st_size == len(payload)
    assert not target.is_relative_to(Path(settings.BASE_DIR) / "var")


def test_mailpit_smtp_delivery_and_api_readback(
    isolated_runtime_environment,
    mailpit,
) -> None:
    del isolated_runtime_environment
    marker = new_ulid()
    subject = f"Kaj Mailpit integration {marker}"
    sent = send_mail(
        subject,
        "Mailpit integration body",
        "no-reply@kaj.test",
        ["admin@kaj.test"],
        fail_silently=False,
    )
    assert sent == 1

    deadline = time.monotonic() + 5
    messages = []
    while time.monotonic() < deadline:
        messages = mailpit.messages()
        if any(message.get("Subject") == subject for message in messages):
            break
        time.sleep(0.1)
    matching = [message for message in messages if message.get("Subject") == subject]
    assert len(matching) == 1
    message = matching[0]
    assert message["From"]["Address"] == "no-reply@kaj.test"
    assert [recipient["Address"] for recipient in message["To"]] == ["admin@kaj.test"]
