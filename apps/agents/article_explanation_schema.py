from collections.abc import Mapping

from apps.agents.schemas import (
    SchemaValidationError,
    StructuredSchema,
    register_structured_schema,
)

ARTICLE_EXPLANATION_SCHEMA_KEY = "article-selection-explanation.v1"
_MAX_EXPLANATION_BYTES = 48_000


def _validate_explanation(value: object) -> Mapping[str, object]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"explanation_markdown"}
        or not isinstance(value["explanation_markdown"], str)
        or not value["explanation_markdown"].strip()
        or "\x00" in value["explanation_markdown"]
        or len(value["explanation_markdown"].encode("utf-8")) > _MAX_EXPLANATION_BYTES
    ):
        raise SchemaValidationError()
    return {"explanation_markdown": value["explanation_markdown"]}


ARTICLE_EXPLANATION_SCHEMA = StructuredSchema(
    key=ARTICLE_EXPLANATION_SCHEMA_KEY,
    provider_schema={
        "type": "object",
        "properties": {
            "explanation_markdown": {
                "type": "string",
                "minLength": 1,
                "maxLength": _MAX_EXPLANATION_BYTES,
            }
        },
        "required": ["explanation_markdown"],
        "additionalProperties": False,
    },
    validator=_validate_explanation,
    allowed_strategies=("native", "tool"),
)


def register_article_explanation_schema() -> None:
    register_structured_schema(ARTICLE_EXPLANATION_SCHEMA, replace=True)


__all__ = [
    "ARTICLE_EXPLANATION_SCHEMA",
    "ARTICLE_EXPLANATION_SCHEMA_KEY",
    "register_article_explanation_schema",
]
