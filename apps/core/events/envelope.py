import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

from apps.core.ids import is_ulid, normalize_ulid
from apps.core.time.clock import require_aware

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type PayloadValidator = Callable[[Mapping[str, JsonValue]], None]

_EVENT_TYPE = re.compile(
    r"^(?P<domain>[a-z][a-z0-9_]*)\.(?P<fact>[a-z][a-z0-9_]*)\.v(?P<version>[1-9][0-9]*)$"
)
_AGGREGATE_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_AGGREGATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,127}$")
_TRACE_CODE = re.compile(r"^trc_[0-9a-hjkmnp-tv-z]{26}$")
_CREDENTIAL_URL = re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|redis|rediss)://[^@\s]+@")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")
_MAX_PAYLOAD_BYTES = 65_536
_FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "body",
        "body_source",
        "client_ip",
        "connection_string",
        "content",
        "cookie",
        "database_url",
        "email_body",
        "email_code",
        "one_time_code",
        "password",
        "passphrase",
        "path",
        "private_key",
        "raw_ip",
        "secret",
        "storage_path",
        "token",
        "verification_code",
    }
)


class EventValidationError(ValueError):
    """A safe event contract failure that never includes the rejected value."""


def _validate_string(value: str, field_name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EventValidationError(f"Invalid event field: {field_name}")
    return value


def _normalize_payload(payload: Mapping[str, object]) -> dict[str, JsonValue]:
    if not isinstance(payload, Mapping):
        raise EventValidationError("Event payload must be an object")
    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        normalized = json.loads(serialized)
    except (TypeError, ValueError):
        raise EventValidationError("Event payload must contain JSON values") from None
    if not isinstance(normalized, dict):
        raise EventValidationError("Event payload must be an object")
    if len(serialized.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise EventValidationError("Event payload exceeds the size limit")
    _reject_sensitive_values(normalized)
    return normalized


def _reject_sensitive_values(value: JsonValue) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.casefold().replace("-", "_")
            if normalized_key in _FORBIDDEN_KEYS:
                raise EventValidationError("Event payload contains a forbidden field")
            _reject_sensitive_values(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_sensitive_values(item)
        return
    if isinstance(value, str) and any(
        pattern.search(value) for pattern in (_CREDENTIAL_URL, _BEARER, _PRIVATE_KEY)
    ):
        raise EventValidationError("Event payload contains a forbidden value")


@dataclass(frozen=True, slots=True)
class EventDefinition:
    event_type: str
    validate: PayloadValidator

    def __post_init__(self) -> None:
        _validate_string(self.event_type, "event_type", _EVENT_TYPE)
        if not callable(self.validate):
            raise TypeError("Event payload validator must be callable")

    @property
    def schema_version(self) -> int:
        match = _EVENT_TYPE.fullmatch(self.event_type)
        assert match is not None
        return int(match.group("version"))

    def validate_payload(self, payload: Mapping[str, object]) -> dict[str, JsonValue]:
        normalized = _normalize_payload(payload)
        try:
            self.validate(MappingProxyType(normalized))
        except EventValidationError:
            raise
        except (KeyError, TypeError, ValueError):
            raise EventValidationError(
                "Event payload does not match its schema"
            ) from None
        return normalized


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    schema_version: int
    occurred_at: datetime
    actor_id: UUID | None
    aggregate_type: str
    aggregate_id: str
    trace_code: str
    payload: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if not is_ulid(self.event_id):
            raise EventValidationError("Invalid event field: event_id")
        match = _EVENT_TYPE.fullmatch(self.event_type)
        if match is None or int(match.group("version")) != self.schema_version:
            raise EventValidationError("Invalid event field: schema_version")
        require_aware(self.occurred_at)
        if self.actor_id is not None and not isinstance(self.actor_id, UUID):
            raise EventValidationError("Invalid event field: actor_id")
        _validate_string(self.aggregate_type, "aggregate_type", _AGGREGATE_TYPE)
        _validate_string(self.aggregate_id, "aggregate_id", _AGGREGATE_ID)
        _validate_string(self.trace_code, "trace_code", _TRACE_CODE)
        normalized = _normalize_payload(self.payload)
        object.__setattr__(self, "event_id", normalize_ulid(self.event_id))
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))
        object.__setattr__(self, "payload", MappingProxyType(normalized))

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at.isoformat(),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "trace_code": self.trace_code,
            "payload": dict(self.payload),
        }
