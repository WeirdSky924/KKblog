import re
from collections.abc import Mapping

from apps.agents.public import (
    SchemaValidationError,
    StructuredSchema,
    register_structured_schema,
)
from apps.learning.contracts import (
    KnowledgePointDraft,
    QuestionBankPublicationDraft,
    QuestionDraft,
    QuestionOptionDraft,
    QuestionType,
    VolumeDraft,
)

QUESTION_GENERATION_PROFILE_KEY = "question-generation"
QUESTION_GENERATION_SCHEMA_KEY = "question-generation.v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


def _mapping(value: object, fields: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise SchemaValidationError()
    return value


def _text(value: object, *, maximum: int, required: bool = True) -> str:
    if (
        not isinstance(value, str)
        or (required and not value.strip())
        or len(value) > maximum
        or "\x00" in value
    ):
        raise SchemaValidationError()
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise SchemaValidationError()
    return value


def _string_list(value: object, *, maximum: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise SchemaValidationError()
    return [_identifier(item) for item in value]


def _validate_question(value: object) -> Mapping[str, object]:
    question = _mapping(
        value,
        {
            "logical_id",
            "ordinal",
            "question_type",
            "stem_markdown",
            "options",
            "correct_option_ids",
            "boolean_answer",
            "reference_answer",
            "scoring_points",
            "explanation_markdown",
            "knowledge_point_ids",
        },
    )
    if (
        not isinstance(question["ordinal"], int)
        or isinstance(question["ordinal"], bool)
        or question["ordinal"] < 1
        or question["question_type"] not in QuestionType.values
        or not isinstance(question["boolean_answer"], (bool, type(None)))
    ):
        raise SchemaValidationError()
    _identifier(question["logical_id"])
    _text(question["stem_markdown"], maximum=8_000)
    _text(question["reference_answer"], maximum=4_000, required=False)
    _text(question["explanation_markdown"], maximum=8_000)
    options = question["options"]
    if not isinstance(options, list) or len(options) > 8:
        raise SchemaValidationError()
    for raw_option in options:
        option = _mapping(raw_option, {"option_id", "text"})
        _identifier(option["option_id"])
        _text(option["text"], maximum=500)
    _string_list(question["correct_option_ids"], maximum=8)
    scoring_points = question["scoring_points"]
    if not isinstance(scoring_points, list) or len(scoring_points) > 20:
        raise SchemaValidationError()
    for scoring_point in scoring_points:
        _text(scoring_point, maximum=500)
    knowledge_point_ids = _string_list(
        question["knowledge_point_ids"],
        maximum=4_000,
    )
    if not knowledge_point_ids:
        raise SchemaValidationError()
    return question


def _validate_generation(value: object) -> Mapping[str, object]:
    result = _mapping(
        value,
        {
            "knowledge_points",
            "volumes",
            "omitted_knowledge_point_ids",
            "tag_names",
        },
    )
    points = result["knowledge_points"]
    if not isinstance(points, list) or len(points) > 4_000:
        raise SchemaValidationError()
    for raw_point in points:
        point = _mapping(
            raw_point,
            {"logical_id", "title", "importance", "source_unit_ids"},
        )
        _identifier(point["logical_id"])
        _text(point["title"], maximum=300)
        source_unit_ids = _string_list(point["source_unit_ids"], maximum=128)
        if not source_unit_ids:
            raise SchemaValidationError()
        if (
            not isinstance(point["importance"], int)
            or isinstance(point["importance"], bool)
            or not 1 <= point["importance"] <= 100
        ):
            raise SchemaValidationError()
    volumes = result["volumes"]
    if not isinstance(volumes, list) or len(volumes) > 2:
        raise SchemaValidationError()
    for raw_volume in volumes:
        volume = _mapping(raw_volume, {"volume_number", "questions"})
        if (
            not isinstance(volume["volume_number"], int)
            or isinstance(volume["volume_number"], bool)
            or not 1 <= volume["volume_number"] <= 2_000
        ):
            raise SchemaValidationError()
        questions = volume["questions"]
        if not isinstance(questions, list) or not 1 <= len(questions) <= 2_000:
            raise SchemaValidationError()
        for question in questions:
            _validate_question(question)
    _string_list(result["omitted_knowledge_point_ids"], maximum=4_000)
    tags = result["tag_names"]
    # An empty tag list is a valid provider result; the normalizer supplies the
    # stable server-owned fallback label before publication validation.
    if not isinstance(tags, list) or len(tags) > 20:
        raise SchemaValidationError()
    for tag in tags:
        _text(tag, maximum=80)
    return result


def _semantic_error(path: str, message: str) -> None:
    raise SchemaValidationError(
        "agents.response_semantics_invalid.v1",
        path=path,
        expected=message,
    )


def _normalize_generation(value: Mapping[str, object]) -> Mapping[str, object]:
    """Canonicalize the union-shaped question fields before semantic checks.

    The provider schema keeps one stable object shape for every question type so
    strict provider strategies can be used consistently.  Fields belonging to
    another question type are therefore deterministic representation details,
    not additional business content.  Clearing them here prevents a model that
    repeats an explanation in an inapplicable field from being rejected as a
    different question.
    """
    normalized = dict(value)
    volumes = []
    for raw_volume in value["volumes"]:
        volume = dict(raw_volume)
        questions = []
        for raw_question in raw_volume["questions"]:
            question = dict(raw_question)
            question_type = question["question_type"]
            if question_type in {
                QuestionType.SINGLE_CHOICE,
                QuestionType.MULTIPLE_CHOICE,
                QuestionType.TRUE_FALSE,
            }:
                question["reference_answer"] = ""
                question["scoring_points"] = []
            if question_type in {
                QuestionType.TRUE_FALSE,
                QuestionType.SHORT_ANSWER,
            }:
                question["options"] = []
                question["correct_option_ids"] = []
            if question_type == QuestionType.SHORT_ANSWER:
                question["boolean_answer"] = None
            questions.append(question)
        volume["questions"] = questions
        volumes.append(volume)
    normalized["volumes"] = volumes
    if not normalized["tag_names"]:
        normalized["tag_names"] = ["知识题库"]
    return normalized


def _validate_generation_semantics(
    value: Mapping[str, object],
) -> Mapping[str, object]:
    points = value["knowledge_points"]
    point_ids = [item["logical_id"] for item in points]
    if len(point_ids) != len(set(point_ids)):
        _semantic_error("$.knowledge_points", "unique logical_id")
    point_id_set = set(point_ids)
    omitted = value["omitted_knowledge_point_ids"]
    if not set(omitted) <= point_id_set:
        _semantic_error("$.omitted_knowledge_point_ids", "known logical_id")

    volumes = value["volumes"]
    question_ids: set[str] = set()
    covered: set[str] = set()
    for volume_index, volume in enumerate(volumes):
        questions = volume["questions"]
        for question_index, question in enumerate(questions):
            path = f"$.volumes[{volume_index}].questions[{question_index}]"
            logical_id = question["logical_id"]
            if logical_id in question_ids:
                _semantic_error(f"{path}.logical_id", "unique logical_id")
            question_ids.add(logical_id)
            question_type = question["question_type"]
            options = question["options"]
            option_ids = [option["option_id"] for option in options]
            if len(option_ids) != len(set(option_ids)):
                _semantic_error(f"{path}.options", "unique option_id")
            correct_ids = question["correct_option_ids"]
            if not set(correct_ids) <= set(option_ids):
                _semantic_error(f"{path}.correct_option_ids", "known option_id")
            if question_type == QuestionType.SINGLE_CHOICE:
                if (
                    not options
                    or len(correct_ids) != 1
                    or question["boolean_answer"] is not None
                ):
                    _semantic_error(path, "single-choice option and answer shape")
            elif question_type == QuestionType.MULTIPLE_CHOICE:
                if (
                    not options
                    or not 2 <= len(correct_ids) < len(options)
                    or question["boolean_answer"] is not None
                ):
                    _semantic_error(path, "multiple-choice option and answer shape")
            elif question_type == QuestionType.TRUE_FALSE:
                if (
                    options
                    or correct_ids
                    or not isinstance(question["boolean_answer"], bool)
                ):
                    _semantic_error(path, "true-false answer shape")
            elif question_type == QuestionType.SHORT_ANSWER:
                if options or correct_ids or question["boolean_answer"] is not None:
                    _semantic_error(path, "short-answer shape")
            covered.update(question["knowledge_point_ids"])
    if covered & set(omitted):
        _semantic_error("$.omitted_knowledge_point_ids", "not covered by a question")
    if not covered <= point_id_set:
        _semantic_error("$.volumes", "questions reference known knowledge points")
    return dict(value)


_OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "option_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "text": {"type": "string", "minLength": 1, "maxLength": 500},
    },
    "required": ["option_id", "text"],
    "additionalProperties": False,
}
_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "logical_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "ordinal": {"type": "integer", "minimum": 1, "maximum": 2_000},
        "question_type": {"type": "string", "enum": list(QuestionType.values)},
        "stem_markdown": {"type": "string", "minLength": 1, "maxLength": 8_000},
        "options": {"type": "array", "maxItems": 8, "items": _OPTION_SCHEMA},
        "correct_option_ids": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
        },
        "boolean_answer": {"type": ["boolean", "null"]},
        "reference_answer": {"type": "string", "maxLength": 4_000},
        "scoring_points": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "explanation_markdown": {
            "type": "string",
            "minLength": 1,
            "maxLength": 8_000,
        },
        "knowledge_point_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4_000,
            "items": {"type": "string", "minLength": 1, "maxLength": 64},
        },
    },
    "required": [
        "logical_id",
        "ordinal",
        "question_type",
        "stem_markdown",
        "options",
        "correct_option_ids",
        "boolean_answer",
        "reference_answer",
        "scoring_points",
        "explanation_markdown",
        "knowledge_point_ids",
    ],
    "additionalProperties": False,
}
QUESTION_GENERATION_SCHEMA = StructuredSchema(
    key=QUESTION_GENERATION_SCHEMA_KEY,
    provider_schema={
        "type": "object",
        "properties": {
            "knowledge_points": {
                "type": "array",
                "minItems": 0,
                "maxItems": 4_000,
                "items": {
                    "type": "object",
                    "properties": {
                        "logical_id": {"type": "string", "maxLength": 64},
                        "title": {"type": "string", "maxLength": 300},
                        "importance": {"type": "integer", "minimum": 1, "maximum": 100},
                        "source_unit_ids": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 128,
                            "items": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 64,
                            },
                        },
                    },
                    "required": [
                        "logical_id",
                        "title",
                        "importance",
                        "source_unit_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "volumes": {
                "type": "array",
                "minItems": 0,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "volume_number": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 2_000,
                        },
                        "questions": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 2_000,
                            "items": _QUESTION_SCHEMA,
                        },
                    },
                    "required": ["volume_number", "questions"],
                    "additionalProperties": False,
                },
            },
            "omitted_knowledge_point_ids": {
                "type": "array",
                "maxItems": 4_000,
                "items": {"type": "string", "maxLength": 64},
            },
            "tag_names": {
                "type": "array",
                "minItems": 0,
                "maxItems": 20,
                "items": {"type": "string", "minLength": 1, "maxLength": 80},
            },
        },
        "required": [
            "knowledge_points",
            "volumes",
            "omitted_knowledge_point_ids",
            "tag_names",
        ],
        "additionalProperties": False,
    },
    validator=_validate_generation,
    normalizer=_normalize_generation,
    semantic_validator=_validate_generation_semantics,
    allowed_strategies=("native", "tool"),
)


def register_question_generation_schema() -> None:
    register_structured_schema(QUESTION_GENERATION_SCHEMA, replace=True)


def question_bank_publication_draft(value: object) -> QuestionBankPublicationDraft:
    normalized = QUESTION_GENERATION_SCHEMA.validate(value)
    return QuestionBankPublicationDraft(
        knowledge_points=tuple(
            KnowledgePointDraft(
                logical_id=point["logical_id"],
                title=point["title"],
                importance=point["importance"],
                source_unit_ids=tuple(point["source_unit_ids"]),
            )
            for point in normalized["knowledge_points"]
        ),
        volumes=tuple(
            VolumeDraft(
                volume_number=volume["volume_number"],
                questions=tuple(
                    QuestionDraft(
                        logical_id=question["logical_id"],
                        ordinal=question["ordinal"],
                        question_type=question["question_type"],
                        stem_markdown=question["stem_markdown"],
                        options=tuple(
                            QuestionOptionDraft(
                                option_id=option["option_id"],
                                text=option["text"],
                            )
                            for option in question["options"]
                        ),
                        correct_option_ids=tuple(question["correct_option_ids"]),
                        boolean_answer=question["boolean_answer"],
                        reference_answer=question["reference_answer"],
                        scoring_points=tuple(question["scoring_points"]),
                        explanation_markdown=question["explanation_markdown"],
                        knowledge_point_ids=tuple(question["knowledge_point_ids"]),
                    )
                    for question in volume["questions"]
                ),
            )
            for volume in normalized["volumes"]
        ),
        omitted_knowledge_point_ids=tuple(normalized["omitted_knowledge_point_ids"]),
        tag_names=tuple(normalized["tag_names"]),
    )


__all__ = [
    "QUESTION_GENERATION_PROFILE_KEY",
    "QUESTION_GENERATION_SCHEMA",
    "QUESTION_GENERATION_SCHEMA_KEY",
    "question_bank_publication_draft",
    "register_question_generation_schema",
]
