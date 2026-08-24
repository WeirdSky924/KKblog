import re
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from apps.accounts.public import is_administrator
from apps.agents.contracts import AgentCommandError

_SECRET_ALIAS = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_PROFILE_KEY = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
_SCHEMA_KEY = re.compile(r"[a-z][a-z0-9_.-]{2,95}\Z")
_CALLER_TYPE = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_SAFE_IDEMPOTENCY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}\Z")


def require_administrator(actor_id) -> UUID:
    try:
        actor = UUID(str(actor_id))
    except (TypeError, ValueError):
        actor = None
    if actor is None or not is_administrator(actor):
        raise AgentCommandError(
            "agents.administrator_required.v1",
            "需要管理员权限。",
        )
    return actor


def uuid_value(value, *, code: str, message: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise AgentCommandError(code, message) from None


def visible_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AgentCommandError("agents.configuration_invalid.v1", f"{field}不合法。")
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > maximum or "\x00" in value:
        raise AgentCommandError("agents.configuration_invalid.v1", f"{field}不合法。")
    return normalized


def normalize_base_url(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 500:
        raise AgentCommandError(
            "agents.endpoint_url_invalid.v1", "Endpoint 地址不合法。"
        )
    if any(ord(character) < 32 for character in value):
        raise AgentCommandError(
            "agents.endpoint_url_invalid.v1", "Endpoint 地址不合法。"
        )
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        raise AgentCommandError(
            "agents.endpoint_url_invalid.v1", "Endpoint 地址不合法。"
        ) from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65_535
    ):
        raise AgentCommandError(
            "agents.endpoint_url_invalid.v1", "Endpoint 地址不合法。"
        )
    try:
        host = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        raise AgentCommandError(
            "agents.endpoint_url_invalid.v1", "Endpoint 地址不合法。"
        ) from None
    path_parts = parsed.path.split("/")
    if any(part in {".", ".."} for part in path_parts):
        raise AgentCommandError(
            "agents.endpoint_url_invalid.v1", "Endpoint 地址不合法。"
        )
    host_text = f"[{host}]" if ":" in host else host
    netloc = f"{host_text}:{port}" if port is not None else host_text
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def validate_secret_alias(value: object) -> str:
    if not isinstance(value, str) or not _SECRET_ALIAS.fullmatch(value):
        raise AgentCommandError(
            "agents.secret_alias_invalid.v1",
            "服务器密钥引用不合法。",
        )
    return value


def validate_profile_key(value: object) -> str:
    if not isinstance(value, str) or not _PROFILE_KEY.fullmatch(value):
        raise AgentCommandError("agents.profile_invalid.v1", "AGENT 标识不合法。")
    return value


def validate_schema_key(value: object) -> str:
    if not isinstance(value, str) or not _SCHEMA_KEY.fullmatch(value):
        raise AgentCommandError("agents.profile_invalid.v1", "输出 schema 不合法。")
    return value


def validate_caller_type(value: object) -> str:
    if not isinstance(value, str) or not _CALLER_TYPE.fullmatch(value):
        raise AgentCommandError("agents.invocation_invalid.v1", "调用方类型不合法。")
    return value


def validate_bounded_identifier(value: object, *, maximum: int = 128) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or "\x00" in value:
        raise AgentCommandError("agents.invocation_invalid.v1", "调用标识不合法。")
    return value


def validate_idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_IDEMPOTENCY.fullmatch(value):
        raise AgentCommandError("agents.idempotency_invalid.v1", "幂等标识不合法。")
    return value
