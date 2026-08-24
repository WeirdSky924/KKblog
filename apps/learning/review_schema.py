import re
from collections.abc import Mapping

from apps.agents.public import (
    SchemaValidationError,
    StructuredSchema,
    register_structured_schema,
)

KNOWLEDGE_REVIEW_PROFILE_KEY = "knowledge-review"
KNOWLEDGE_REVIEW_SCHEMA_KEY = "knowledge-review.v1"
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_RISK_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def _validate_knowledge_review(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "verdict",
        "reason_code",
        "summary",
        "risk_categories",
    }:
        raise SchemaValidationError()
    verdict = value["verdict"]
    reason_code = value["reason_code"]
    summary = value["summary"]
    risks = value["risk_categories"]
    if (
        verdict not in {"APPROVED", "REJECTED"}
        or not isinstance(reason_code, str)
        or _SAFE_CODE.fullmatch(reason_code) is None
        or not isinstance(summary, str)
        or not 1 <= len(summary.strip()) <= 500
        or "<" in summary
        or ">" in summary
        or "://" in summary
        or not isinstance(risks, list)
        or len(risks) > 16
        or len(set(risks)) != len(risks)
        or any(
            not isinstance(item, str) or _RISK_CODE.fullmatch(item) is None
            for item in risks
        )
    ):
        raise SchemaValidationError()
    return {
        "verdict": verdict,
        "reason_code": reason_code,
        "summary": summary.strip(),
        "risk_categories": list(risks),
    }


KNOWLEDGE_REVIEW_SCHEMA = StructuredSchema(
    key=KNOWLEDGE_REVIEW_SCHEMA_KEY,
    provider_schema={
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["APPROVED", "REJECTED"],
            },
            "reason_code": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_.-]{0,95}$",
            },
            "summary": {"type": "string", "minLength": 1, "maxLength": 500},
            "risk_categories": {
                "type": "array",
                "maxItems": 16,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9_-]{0,63}$",
                },
            },
        },
        "required": [
            "verdict",
            "reason_code",
            "summary",
            "risk_categories",
        ],
        "additionalProperties": False,
    },
    validator=_validate_knowledge_review,
    allowed_strategies=("native", "tool"),
)


def register_learning_review_schema() -> None:
    register_structured_schema(KNOWLEDGE_REVIEW_SCHEMA, replace=True)


__all__ = [
    "KNOWLEDGE_REVIEW_PROFILE_KEY",
    "KNOWLEDGE_REVIEW_SCHEMA",
    "KNOWLEDGE_REVIEW_SCHEMA_KEY",
    "register_learning_review_schema",
]
