import re
from dataclasses import dataclass
from ipaddress import ip_address
from types import MappingProxyType
from uuid import UUID

from apps.operations.models import AuditEntry

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,127}\Z")
_TRACE = re.compile(r"(?:KJ-[A-Za-z0-9-]{3,26}|trc_[0-9a-z]{26})\Z")
_FORBIDDEN_FIELDS = {
    "authorization",
    "body",
    "code",
    "connection",
    "content",
    "cookie",
    "credential",
    "email",
    "password",
    "path",
    "raw",
    "secret",
    "token",
}
_DEFAULT_MAX_LIST_ITEMS = 50
_MAX_SCHEMA_LIST_ITEMS = 200


class AuditRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AuditSchema:
    action: str
    target_type: str
    allowed_fields: frozenset[str]
    max_list_items: int = _DEFAULT_MAX_LIST_ITEMS

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.action):
            raise AuditRejected("Invalid audit action")
        if not _IDENTIFIER.fullmatch(self.target_type):
            raise AuditRejected("Invalid audit target type")
        for field in self.allowed_fields:
            lowered = field.casefold()
            if not _IDENTIFIER.fullmatch(field) or any(
                marker in lowered for marker in _FORBIDDEN_FIELDS
            ):
                raise AuditRejected("Unsafe audit schema field")
        if (
            isinstance(self.max_list_items, bool)
            or not isinstance(self.max_list_items, int)
            or not 1 <= self.max_list_items <= _MAX_SCHEMA_LIST_ITEMS
        ):
            raise AuditRejected("Invalid audit schema list limit")


_SCHEMAS: dict[str, AuditSchema] = {}


def register_audit_schema(schema: AuditSchema, *, replace: bool = False) -> None:
    current = _SCHEMAS.get(schema.action)
    if current is not None and current != schema and not replace:
        raise AuditRejected("Audit schema already registered")
    _SCHEMAS[schema.action] = schema


def registered_audit_schemas() -> MappingProxyType:
    return MappingProxyType(_SCHEMAS)


def _safe_value(value, *, max_list_items: int):
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        if len(value) > 255 or "\x00" in value:
            raise AuditRejected("Unsafe audit value")
        return value
    if isinstance(value, list | tuple):
        if len(value) > max_list_items:
            raise AuditRejected("Unsafe audit value")
        return [_safe_value(item, max_list_items=max_list_items) for item in value]
    raise AuditRejected("Unsafe audit value type")


def _validate_snapshot(
    snapshot: dict[str, object], schema: AuditSchema
) -> dict[str, object]:
    if not isinstance(snapshot, dict):
        raise AuditRejected("Audit snapshot must be an object")
    if not set(snapshot) <= schema.allowed_fields:
        raise AuditRejected("Unknown audit field")
    return {
        key: _safe_value(value, max_list_items=schema.max_list_items)
        for key, value in snapshot.items()
    }


def record_audit_entry(
    *,
    action: str,
    actor_id,
    target_id: str,
    trace_code: str,
    client_ip: str,
    before: dict[str, object],
    after: dict[str, object],
    summary: str = "",
) -> AuditEntry:
    schema = _SCHEMAS.get(action)
    if schema is None:
        raise AuditRejected("Unknown audit action")
    try:
        actor = UUID(str(actor_id))
        parsed_ip = str(ip_address(client_ip))
    except (TypeError, ValueError):
        raise AuditRejected("Invalid audit identity") from None
    if not isinstance(target_id, str) or not 1 <= len(target_id) <= 128:
        raise AuditRejected("Invalid audit target")
    if not _TRACE.fullmatch(trace_code):
        raise AuditRejected("Invalid trace code")
    if not isinstance(summary, str) or len(summary) > 255 or "\x00" in summary:
        raise AuditRejected("Invalid audit summary")
    before_safe = _validate_snapshot(before, schema)
    after_safe = _validate_snapshot(after, schema)
    return AuditEntry.objects.create(
        actor_id=actor,
        action=action,
        target_type=schema.target_type,
        target_id=target_id,
        trace_code=trace_code,
        client_ip=parsed_ip,
        summary=summary,
        before_safe=before_safe,
        after_safe=after_safe,
    )
