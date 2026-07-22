import pytest

from config.environment import (
    ConfigurationError,
    load_isolated_test_database,
    load_isolated_test_mailpit,
    load_isolated_test_redis,
)


def test_isolated_test_database_accepts_only_explicit_loopback_database() -> None:
    config = load_isolated_test_database(
        {
            "KAJ_TEST_DATABASE_URL": (
                "postgresql://kaj_test_runner@127.0.0.1:55432/kaj_test_contracts"
            )
        }
    )
    assert config is not None
    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "kaj_test_contracts"
    assert config["HOST"] == "127.0.0.1"
    assert config["PORT"] == 55432
    assert config["CONN_MAX_AGE"] == 0


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://kaj_test_runner@db.internal:55432/kaj_test_contracts",
        "postgresql://kaj_test_runner@127.0.0.1:55432/blog",
        "postgresql://app@127.0.0.1:55432/kaj_test_contracts",
        "postgresql://kaj_test_runner:password@127.0.0.1:55432/kaj_test_contracts",
        "postgresql://kaj_test_runner@127.0.0.1/kaj_test_contracts",
        "postgresql://kaj_test_runner@127.0.0.1:55432/kaj_test_contracts?sslmode=require",
    ],
)
def test_isolated_test_database_rejects_shared_or_secret_connection(url) -> None:
    with pytest.raises(ConfigurationError, match="KAJ_TEST_DATABASE_URL") as captured:
        load_isolated_test_database({"KAJ_TEST_DATABASE_URL": url})
    assert url not in str(captured.value)


def test_isolated_test_redis_accepts_non_default_loopback_database() -> None:
    url = "redis://127.0.0.1:56379/15"
    assert load_isolated_test_redis({"KAJ_TEST_REDIS_URL": url}) == url


@pytest.mark.parametrize(
    "url",
    [
        "redis://cache.internal:56379/15",
        "redis://127.0.0.1:6379/0",
        "redis://user@127.0.0.1:56379/15",
        "redis://127.0.0.1:56379/15?decode=true",
    ],
)
def test_isolated_test_redis_rejects_shared_or_credentialed_url(url) -> None:
    with pytest.raises(ConfigurationError, match="KAJ_TEST_REDIS_URL") as captured:
        load_isolated_test_redis({"KAJ_TEST_REDIS_URL": url})
    assert url not in str(captured.value)


def test_isolated_test_mailpit_requires_loopback_pair() -> None:
    endpoints = load_isolated_test_mailpit(
        {
            "KAJ_TEST_MAILPIT_SMTP_URL": "smtp://127.0.0.1:11025",
            "KAJ_TEST_MAILPIT_API_URL": "http://127.0.0.1:18025",
        }
    )
    assert endpoints is not None
    assert endpoints.smtp_host == "127.0.0.1"
    assert endpoints.smtp_port == 11025
    assert endpoints.api_url == "http://127.0.0.1:18025"


@pytest.mark.parametrize(
    ("smtp", "api"),
    [
        ("smtp://mail.internal:11025", "http://127.0.0.1:18025"),
        ("smtp://127.0.0.1:11025", "https://127.0.0.1:18025"),
        ("smtp://user@127.0.0.1:11025", "http://127.0.0.1:18025"),
        ("smtp://127.0.0.1:11025", "http://127.0.0.1:18025/api"),
        ("smtp://127.0.0.1:11025", ""),
    ],
)
def test_isolated_test_mailpit_rejects_shared_or_partial_endpoints(smtp, api) -> None:
    with pytest.raises(ConfigurationError) as captured:
        load_isolated_test_mailpit(
            {
                "KAJ_TEST_MAILPIT_SMTP_URL": smtp,
                "KAJ_TEST_MAILPIT_API_URL": api,
            }
        )
    assert smtp not in str(captured.value)
    if api:
        assert api not in str(captured.value)
