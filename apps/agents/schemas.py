import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

_SCHEMA_KEY = re.compile(r"[a-z][a-z0-9_.-]{2,95}\Z")
_MAX_PROVIDER_SCHEMA_BYTES = 65_536
_STRATEGIES = frozenset({"native", "tool", "json_best_effort"})


class SchemaValidationError(ValueError):
    def __init__(
        self,
        code: str = "agents.response_schema_invalid.v1",
        *,
        path: str = "",
        expected: str = "",
        actual: str = "",
    ) -> None:
        super().__init__(code)
        self.code = code
        self.path = path
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True, slots=True)
class ValidatedOutput:
    value: Mapping[str, object]
    schema_key: str
    schema_sha256: str

    def as_mapping(self) -> Mapping[str, object]:
        return dict(self.value)


def _compile_schema(schema: object, *, depth: int = 0) -> None:
    if depth > 16 or not isinstance(schema, Mapping):
        raise ValueError("Invalid structured schema")
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "enum",
        "const",
        "pattern",
        "uniqueItems",
        "description",
        "title",
    }
    if any(key not in allowed for key in schema):
        raise ValueError("Invalid structured schema")
    raw_type = schema.get("type")
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    if not types or any(
        item
        not in {"object", "array", "string", "integer", "number", "boolean", "null"}
        for item in types
    ):
        raise ValueError("Invalid structured schema")
    for key in ("minItems", "maxItems", "minLength", "maxLength"):
        value = schema.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError("Invalid structured schema")
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if minimum is not None and (
        isinstance(minimum, bool) or not isinstance(minimum, int | float)
    ):
        raise ValueError("Invalid structured schema")
    if maximum is not None and (
        isinstance(maximum, bool) or not isinstance(maximum, int | float)
    ):
        raise ValueError("Invalid structured schema")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("Invalid structured schema")
    if "object" in types:
        properties = schema.get("properties")
        required = schema.get("required")
        if (
            not isinstance(properties, Mapping)
            or schema.get("additionalProperties") is not False
            or not isinstance(required, list)
            or any(not isinstance(item, str) for item in required)
            or set(required) - set(properties)
        ):
            raise ValueError("Invalid structured schema")
        for child in properties.values():
            _compile_schema(child, depth=depth + 1)
    if "array" in types:
        if "items" not in schema:
            raise ValueError("Invalid structured schema")
        _compile_schema(schema["items"], depth=depth + 1)
    if (
        "string" in types
        and "pattern" in schema
        and not isinstance(schema["pattern"], str)
    ):
        raise ValueError("Invalid structured schema")
    if "enum" in schema and (
        not isinstance(schema["enum"], list) or not schema["enum"]
    ):
        raise ValueError("Invalid structured schema")


def decode_json_object(raw: bytes | str) -> Mapping[str, object]:
    def pairs(values):
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise SchemaValidationError(
                    "agents.response_duplicate_key.v1", path=f"$.{key}"
                )
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=pairs)
    except SchemaValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise SchemaValidationError("agents.response_invalid.v1") from None
    if not isinstance(value, Mapping):
        raise SchemaValidationError("agents.response_not_object.v1")
    return dict(value)


@dataclass(frozen=True, slots=True)
class SchemaSpec:
    key: str
    provider_schema: Mapping[str, object]
    validator: Callable[[object], Mapping[str, object]]
    normalizer: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None
    semantic_validator: (
        Callable[[Mapping[str, object]], Mapping[str, object]] | None
    ) = None
    allowed_strategies: tuple[str, ...] = ("native", "tool", "json_best_effort")
    schema_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            not _SCHEMA_KEY.fullmatch(self.key)
            or not callable(self.validator)
            or (self.normalizer is not None and not callable(self.normalizer))
            or (
                self.semantic_validator is not None
                and not callable(self.semantic_validator)
            )
            or not self.allowed_strategies
            or any(strategy not in _STRATEGIES for strategy in self.allowed_strategies)
        ):
            raise ValueError("Invalid structured schema")
        try:
            encoded = json.dumps(
                dict(self.provider_schema),
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (TypeError, ValueError):
            raise ValueError("Invalid structured schema") from None
        if not encoded or len(encoded) > _MAX_PROVIDER_SCHEMA_BYTES:
            raise ValueError("Invalid structured schema")
        _compile_schema(self.provider_schema)
        if not self.schema_sha256:
            object.__setattr__(self, "schema_sha256", sha256(encoded).hexdigest())

    def decode(self, value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise SchemaValidationError(
                path="$", expected="object", actual=type(value).__name__
            )
        return dict(value)

    def validate_structure(self, value: object) -> Mapping[str, object]:
        try:
            result = self.validator(value)
        except SchemaValidationError:
            raise
        except Exception:
            raise SchemaValidationError() from None
        if not isinstance(result, Mapping):
            raise SchemaValidationError(
                path="$", expected="object", actual=type(result).__name__
            )
        return dict(result)

    def normalize(self, value: Mapping[str, object]) -> Mapping[str, object]:
        if self.normalizer is None:
            return dict(value)
        try:
            result = self.normalizer(value)
        except SchemaValidationError:
            raise
        except Exception:
            raise SchemaValidationError(
                "agents.response_normalization_invalid.v1"
            ) from None
        if not isinstance(result, Mapping):
            raise SchemaValidationError("agents.response_normalization_invalid.v1")
        return dict(result)

    def validate_semantics(self, value: Mapping[str, object]) -> Mapping[str, object]:
        if self.semantic_validator is None:
            return dict(value)
        try:
            result = self.semantic_validator(value)
        except SchemaValidationError:
            raise
        except Exception:
            raise SchemaValidationError(
                "agents.response_semantics_invalid.v1"
            ) from None
        if not isinstance(result, Mapping):
            raise SchemaValidationError("agents.response_semantics_invalid.v1")
        return dict(result)

    def validate(self, value: object) -> Mapping[str, object]:
        decoded = self.decode(value)
        structured = self.validate_structure(decoded)
        normalized = self.normalize(structured)
        return self.validate_semantics(normalized)

    def validate_output(self, value: object) -> ValidatedOutput:
        normalized = self.validate(value)
        return ValidatedOutput(
            value=dict(normalized),
            schema_key=self.key,
            schema_sha256=self.schema_sha256,
        )


# Compatibility facade: existing callers keep StructuredSchema, while all
# registrations and runtime lookups use the compiled SchemaSpec implementation.
StructuredSchema = SchemaSpec
_SCHEMAS: dict[str, SchemaSpec] = {}


def register_structured_schema(schema: SchemaSpec, *, replace: bool = False) -> None:
    if not isinstance(schema, SchemaSpec):
        raise ValueError("Invalid structured schema")
    current = _SCHEMAS.get(schema.key)
    if current is not None and current != schema and not replace:
        raise ValueError("Structured schema already registered")
    _SCHEMAS[schema.key] = schema


def structured_schema(key: str) -> SchemaSpec:
    try:
        return _SCHEMAS[key]
    except (KeyError, TypeError):
        raise SchemaValidationError("agents.schema_unavailable.v1") from None


__all__ = [
    "SchemaSpec",
    "SchemaValidationError",
    "StructuredSchema",
    "ValidatedOutput",
    "decode_json_object",
    "register_structured_schema",
    "structured_schema",
]
