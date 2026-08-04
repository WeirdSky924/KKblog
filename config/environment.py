import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

_RESERVED_TLDS = {"example", "invalid", "localhost", "test"}


class ConfigurationError(RuntimeError):
    """A safe startup error that identifies a key, never its value."""


@dataclass(frozen=True, slots=True)
class SmtpEnvironment:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    use_tls: bool
    use_ssl: bool
    from_email: str


@dataclass(frozen=True, slots=True)
class ProductionEnvironment:
    secret_key: str = field(repr=False)
    public_url: str
    public_host: str
    admin_email: str
    smtp: SmtpEnvironment
    database: dict[str, object] = field(repr=False)
    redis_url: str = field(repr=False)
    media_root: Path
    initial_admin_password: str = field(repr=False)
    trusted_proxy_cidrs: tuple[str, ...]
    umami_database_url: str = field(repr=False)
    umami_website_id: str


@dataclass(frozen=True, slots=True)
class TestMailpitEndpoints:
    smtp_host: str
    smtp_port: int
    api_url: str


@dataclass(frozen=True, slots=True)
class DevelopmentMailpitEndpoint:
    host: str
    port: int


def _missing(name: str) -> ConfigurationError:
    return ConfigurationError(f"Missing required production configuration: {name}")


def _invalid(name: str) -> ConfigurationError:
    return ConfigurationError(f"Invalid production configuration: {name}")


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise _missing(name)
    return value


def _validate_secret(value: str, name: str, minimum: int) -> str:
    lowered = value.casefold()
    weak_markers = ("changeme", "development", "password", "secret", "test-only")
    if len(value) < minimum or any(marker in lowered for marker in weak_markers):
        raise _invalid(name)
    return value


def _real_domain(host: str, name: str) -> str:
    normalized = host.rstrip(".").casefold()
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        pass
    else:
        raise _invalid(name)

    try:
        ascii_host = normalized.encode("idna").decode("ascii")
    except UnicodeError:
        raise _invalid(name) from None
    labels = ascii_host.split(".")
    if len(labels) < 2 or labels[-1] in _RESERVED_TLDS:
        raise _invalid(name)
    label_pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
    if any(not label_pattern.fullmatch(label) for label in labels):
        raise _invalid(name)
    return ascii_host


def _public_url(value: str) -> tuple[str, str]:
    name = "KAJ_PUBLIC_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise _invalid(name) from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid(name)
    host = _real_domain(parsed.hostname, name)
    return f"https://{host}", host


def _email(value: str, name: str) -> str:
    try:
        validate_email(value)
    except ValidationError:
        raise _invalid(name) from None
    domain = value.rsplit("@", 1)[1]
    _real_domain(domain, name)
    return value


def _smtp_host(value: str) -> str:
    name = "EMAIL_HOST"
    normalized = value.rstrip(".").casefold()
    if not normalized or normalized != value.strip().rstrip(".").casefold():
        raise _invalid(name)
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            ascii_host = normalized.encode("idna").decode("ascii")
        except UnicodeError:
            raise _invalid(name) from None
        label_pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
        labels = ascii_host.split(".")
        if any(not label_pattern.fullmatch(label) for label in labels):
            raise _invalid(name) from None
        return ascii_host
    if address.is_unspecified or address.is_multicast:
        raise _invalid(name)
    return str(address)


def _smtp_port(value: str) -> int:
    name = "EMAIL_PORT"
    try:
        port = int(value)
    except ValueError:
        raise _invalid(name) from None
    if not 1 <= port <= 65_535:
        raise _invalid(name)
    return port


def _boolean(values: Mapping[str, str], name: str) -> bool:
    value = _required(values, name).casefold()
    if value not in {"true", "false"}:
        raise _invalid(name)
    return value == "true"


def _smtp_environment(values: Mapping[str, str]) -> SmtpEnvironment:
    username = values.get("EMAIL_HOST_USER", "").strip()
    password = values.get("EMAIL_HOST_PASSWORD", "")
    if username and not password:
        raise _missing("EMAIL_HOST_PASSWORD")
    if password and not username:
        raise _missing("EMAIL_HOST_USER")
    use_tls = _boolean(values, "EMAIL_USE_TLS")
    use_ssl = _boolean(values, "EMAIL_USE_SSL")
    if use_tls and use_ssl:
        raise _invalid("EMAIL_TRANSPORT")
    return SmtpEnvironment(
        host=_smtp_host(_required(values, "EMAIL_HOST")),
        port=_smtp_port(_required(values, "EMAIL_PORT")),
        username=username,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        from_email=_email(
            _required(values, "DEFAULT_FROM_EMAIL"), "DEFAULT_FROM_EMAIL"
        ),
    )


def _database(value: str) -> dict[str, object]:
    name = "DATABASE_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port or 5432
    except ValueError:
        raise _invalid(name) from None
    database_name = unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in {"postgres", "postgresql"} or not all(
        (parsed.hostname, parsed.username, parsed.password, database_name)
    ):
        raise _invalid(name)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": port,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }


def load_umami_database_url(
    values: Mapping[str, str], *, required: bool = False
) -> str:
    name = "KAJ_UMAMI_DATABASE_URL"
    value = values.get(name, "").strip()
    if not value:
        if required:
            raise _missing(name)
        return ""
    try:
        parsed = urlsplit(value)
        port = parsed.port or 5432
    except ValueError:
        raise _invalid(name) from None
    database_name = unquote(parsed.path.lstrip("/"))
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not parsed.username
        or parsed.password is None
        or database_name != "umami"
        or not 1 <= port <= 65_535
        or parsed.fragment
    ):
        raise _invalid(name)
    return value


def load_umami_website_id(values: Mapping[str, str], *, required: bool = False) -> str:
    name = "KAJ_UMAMI_WEBSITE_ID"
    value = values.get(name, "").strip()
    if not value:
        if required:
            raise _missing(name)
        return ""
    try:
        website_id = UUID(value)
    except (AttributeError, ValueError):
        raise _invalid(name) from None
    return str(website_id)


def load_development_database(
    values: Mapping[str, str],
) -> dict[str, object] | None:
    value = values.get("DATABASE_URL", "").strip()
    if not value:
        return None
    name = "DATABASE_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port or 5432
    except ValueError:
        raise _invalid(name) from None
    database_name = unquote(parsed.path.lstrip("/"))
    username = unquote(parsed.username or "")
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1", "postgres"}
        or port != 5432
        or username != "kaj"
        or parsed.password is None
        or database_name != "kaj"
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid(name)
    return _database(value)


def load_development_redis(values: Mapping[str, str]) -> str:
    value = values.get("REDIS_URL", "").strip() or "redis://localhost:6379/0"
    name = "REDIS_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port
        database = int(parsed.path.lstrip("/"))
    except (TypeError, ValueError):
        raise _invalid(name) from None
    if (
        parsed.scheme != "redis"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1", "redis"}
        or port != 6379
        or parsed.username is not None
        or parsed.password is not None
        or database != 0
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid(name)
    return value


def load_development_mailpit(
    values: Mapping[str, str],
) -> DevelopmentMailpitEndpoint:
    host = values.get("EMAIL_HOST", "").strip() or "localhost"
    raw_port = values.get("EMAIL_PORT", "").strip() or "1025"
    try:
        port = int(raw_port)
    except ValueError:
        raise _invalid("EMAIL_PORT") from None
    if host not in {"127.0.0.1", "localhost", "::1", "mailpit"}:
        raise _invalid("EMAIL_HOST")
    if port != 1025:
        raise _invalid("EMAIL_PORT")
    return DevelopmentMailpitEndpoint(host=host, port=port)


def load_trusted_proxy_cidrs(
    values: Mapping[str, str], *, required: bool = False
) -> tuple[str, ...]:
    name = "KAJ_TRUSTED_PROXY_CIDRS"
    raw = values.get(name, "").strip()
    if not raw:
        if required:
            raise _missing(name)
        return ()
    items = [item.strip() for item in raw.split(",")]
    if not 1 <= len(items) <= 16 or any(not item for item in items):
        raise _invalid(name)
    result: list[str] = []
    for item in items:
        try:
            network = ipaddress.ip_network(item, strict=False)
        except ValueError:
            raise _invalid(name) from None
        if network.prefixlen == 0:
            raise _invalid(name)
        normalized = str(network)
        if normalized not in result:
            result.append(normalized)
    return tuple(result)


def load_isolated_test_database(values: Mapping[str, str]) -> dict[str, object] | None:
    value = values.get("KAJ_TEST_DATABASE_URL", "").strip()
    if not value:
        return None
    name = "KAJ_TEST_DATABASE_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise _invalid(name) from None
    database_name = unquote(parsed.path.lstrip("/"))
    username = unquote(parsed.username or "")
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or not 1_024 <= port <= 65_535
        or username != "kaj_test_runner"
        or parsed.password is not None
        or not database_name.startswith("kaj_test_")
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid(name)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": username,
        "HOST": parsed.hostname,
        "PORT": port,
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"sslmode": "disable"},
    }


def load_isolated_umami_database_url(values: Mapping[str, str]) -> str | None:
    value = values.get("KAJ_TEST_UMAMI_DATABASE_URL", "").strip()
    if not value:
        return None
    name = "KAJ_TEST_UMAMI_DATABASE_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise _invalid(name) from None
    database_name = unquote(parsed.path.lstrip("/"))
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or not 1_024 <= port <= 65_535
        or parsed.username != "kaj_test_runner"
        or parsed.password is not None
        or not database_name.startswith("kaj_test_")
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid(name)
    return value


def load_isolated_test_redis(values: Mapping[str, str]) -> str | None:
    value = values.get("KAJ_TEST_REDIS_URL", "").strip()
    if not value:
        return None
    name = "KAJ_TEST_REDIS_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port
        database = int(parsed.path.lstrip("/"))
    except (TypeError, ValueError):
        raise _invalid(name) from None
    if (
        parsed.scheme != "redis"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or not 1_024 <= port <= 65_535
        or parsed.username is not None
        or parsed.password is not None
        or not 1 <= database <= 15
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid(name)
    return value


def load_isolated_test_mailpit(
    values: Mapping[str, str],
) -> TestMailpitEndpoints | None:
    smtp_value = values.get("KAJ_TEST_MAILPIT_SMTP_URL", "").strip()
    api_value = values.get("KAJ_TEST_MAILPIT_API_URL", "").strip()
    if not smtp_value and not api_value:
        return None
    if not smtp_value or not api_value:
        raise _missing("KAJ_TEST_MAILPIT_SMTP_URL/KAJ_TEST_MAILPIT_API_URL")
    try:
        smtp = urlsplit(smtp_value)
        api = urlsplit(api_value)
        smtp_port = smtp.port
        api_port = api.port
    except ValueError:
        raise _invalid("KAJ_TEST_MAILPIT_ENDPOINTS") from None
    loopback = {"127.0.0.1", "localhost", "::1"}
    if (
        smtp.scheme != "smtp"
        or smtp.hostname not in loopback
        or smtp_port is None
        or not 1_024 <= smtp_port <= 65_535
        or smtp.username is not None
        or smtp.password is not None
        or smtp.path not in {"", "/"}
        or smtp.query
        or smtp.fragment
        or api.scheme != "http"
        or api.hostname not in loopback
        or api_port is None
        or not 1_024 <= api_port <= 65_535
        or api.username is not None
        or api.password is not None
        or api.path not in {"", "/"}
        or api.query
        or api.fragment
    ):
        raise _invalid("KAJ_TEST_MAILPIT_ENDPOINTS")
    return TestMailpitEndpoints(
        smtp_host=smtp.hostname,
        smtp_port=smtp_port,
        api_url=f"http://{api.hostname}:{api_port}",
    )


def _redis(value: str) -> str:
    name = "REDIS_URL"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise _invalid(name) from None
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname or port is None:
        raise _invalid(name)
    if parsed.query or parsed.fragment:
        raise _invalid(name)
    return value


def _media_root(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path in {Path("/"), Path("/tmp")}:
        raise _invalid("KAJ_MEDIA_ROOT")
    return path


def _initial_password(value: str) -> str:
    name = "KAJ_INITIAL_ADMIN_PASSWORD"
    _validate_secret(value, name, 16)
    classes = (
        any(char.islower() for char in value),
        any(char.isupper() for char in value),
        any(char.isdigit() for char in value),
        any(not char.isalnum() for char in value),
    )
    if not all(classes):
        raise _invalid(name)
    return value


def load_production_environment(values: Mapping[str, str]) -> ProductionEnvironment:
    secret_key = _validate_secret(
        _required(values, "DJANGO_SECRET_KEY"), "DJANGO_SECRET_KEY", 50
    )
    public_url, public_host = _public_url(_required(values, "KAJ_PUBLIC_URL"))
    admin_email = _email(_required(values, "KAJ_ADMIN_EMAIL"), "KAJ_ADMIN_EMAIL")
    smtp = _smtp_environment(values)
    database = _database(_required(values, "DATABASE_URL"))
    redis_url = _redis(_required(values, "REDIS_URL"))
    media_root = _media_root(_required(values, "KAJ_MEDIA_ROOT"))
    initial_password = _initial_password(
        _required(values, "KAJ_INITIAL_ADMIN_PASSWORD")
    )
    trusted_proxy_cidrs = load_trusted_proxy_cidrs(values, required=True)
    umami_database_url = load_umami_database_url(values, required=True)
    parsed_umami = urlsplit(umami_database_url)
    if (
        parsed_umami.hostname == database["HOST"]
        and (parsed_umami.port or 5432) == database["PORT"]
        and unquote(parsed_umami.path.lstrip("/")) == database["NAME"]
    ):
        raise _invalid("KAJ_UMAMI_DATABASE_URL")
    umami_website_id = load_umami_website_id(values, required=True)
    return ProductionEnvironment(
        secret_key=secret_key,
        public_url=public_url,
        public_host=public_host,
        admin_email=admin_email,
        smtp=smtp,
        database=database,
        redis_url=redis_url,
        media_root=media_root,
        initial_admin_password=initial_password,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
        umami_database_url=umami_database_url,
        umami_website_id=umami_website_id,
    )
