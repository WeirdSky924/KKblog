import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from hashlib import sha256

from apps.learning.contracts import (
    KnowledgePointDraft,
    LearningCommandError,
    QuestionBankCoverageState,
    QuestionBankPublicationDraft,
    QuestionDraft,
    QuestionOptionDraft,
    QuestionType,
    VolumeDraft,
)
from apps.media.public import RenderingError, render_markdown

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
MAX_BANK_PAYLOAD_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ValidatedPublication:
    knowledge_points: tuple[KnowledgePointDraft, ...]
    volumes: tuple[VolumeDraft, ...]
    omitted_knowledge_point_ids: tuple[str, ...]
    tag_names: tuple[str, ...]
    coverage_state: QuestionBankCoverageState
    covered_count: int
    omitted_count: int


def _invalid() -> LearningCommandError:
    return LearningCommandError(
        "learning.question_schema_invalid.v1", "题库内容不符合固定 schema。"
    )


def _visible(value: object, *, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise _invalid()
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        (required and not normalized)
        or len(normalized) > maximum
        or "\x00" in normalized
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in normalized
        )
    ):
        raise _invalid()
    return normalized


def _markdown(value: object, *, maximum: int = 8_000) -> str:
    normalized = _visible(value, maximum=maximum)
    try:
        render_markdown(normalized)
    except RenderingError:
        raise _invalid() from None
    return normalized


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise _invalid()
    return value


def _options(values: object) -> tuple[QuestionOptionDraft, ...]:
    if not isinstance(values, tuple) or not 2 <= len(values) <= 8:
        raise _invalid()
    result = tuple(
        QuestionOptionDraft(
            _identifier(value.option_id),
            _visible(value.text, maximum=500),
        )
        if isinstance(value, QuestionOptionDraft)
        else (_ for _ in ()).throw(_invalid())
        for value in values
    )
    if len({value.option_id for value in result}) != len(result):
        raise _invalid()
    return result


def validate_questions(
    questions: tuple[QuestionDraft, ...],
    *,
    allowed_types: tuple[str, ...],
    knowledge_point_ids: frozenset[str],
    maximum_questions: int,
    allow_noncontiguous_ordinals: bool = False,
) -> tuple[QuestionDraft, ...]:
    if (
        not isinstance(questions, tuple)
        or not 1 <= len(questions) <= maximum_questions
        or (
            not allow_noncontiguous_ordinals
            and tuple(question.ordinal for question in questions)
            != tuple(range(1, len(questions) + 1))
        )
    ):
        raise _invalid()
    normalized = []
    logical_ids = set()
    stems = set()
    for question in questions:
        if not isinstance(question, QuestionDraft):
            raise _invalid()
        logical_id = _identifier(question.logical_id)
        if logical_id in logical_ids:
            raise _invalid()
        logical_ids.add(logical_id)
        try:
            question_type = QuestionType(question.question_type)
        except (TypeError, ValueError):
            raise _invalid() from None
        if question_type not in allowed_types:
            raise _invalid()
        stem = _markdown(question.stem_markdown)
        stem_key = " ".join(stem.split()).casefold()
        if stem_key in stems:
            raise _invalid()
        stems.add(stem_key)
        explanation = _markdown(question.explanation_markdown)
        point_ids = tuple(
            dict.fromkeys(_identifier(item) for item in question.knowledge_point_ids)
        )
        if not point_ids or not set(point_ids) <= knowledge_point_ids:
            raise _invalid()

        options: tuple[QuestionOptionDraft, ...] = ()
        correct_ids: tuple[str, ...] = ()
        boolean_answer = None
        reference_answer = ""
        scoring_points: tuple[str, ...] = ()
        if question_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
        }:
            options = _options(question.options)
            option_ids = {option.option_id for option in options}
            if not isinstance(question.correct_option_ids, tuple):
                raise _invalid()
            correct_ids = tuple(
                dict.fromkeys(_identifier(item) for item in question.correct_option_ids)
            )
            if not set(correct_ids) <= option_ids:
                raise _invalid()
            if question_type == QuestionType.SINGLE_CHOICE and len(correct_ids) != 1:
                raise _invalid()
            if question_type == QuestionType.MULTIPLE_CHOICE and not (
                2 <= len(correct_ids) < len(options)
            ):
                raise _invalid()
            if (
                question.boolean_answer is not None
                or question.reference_answer
                or question.scoring_points
            ):
                raise _invalid()
        elif question_type == QuestionType.TRUE_FALSE:
            if (
                question.options
                or question.correct_option_ids
                or type(question.boolean_answer) is not bool
                or question.reference_answer
                or question.scoring_points
            ):
                raise _invalid()
            boolean_answer = question.boolean_answer
        else:
            if (
                question.options
                or question.correct_option_ids
                or question.boolean_answer is not None
                or not isinstance(question.scoring_points, tuple)
                or not 1 <= len(question.scoring_points) <= 20
            ):
                raise _invalid()
            reference_answer = _visible(question.reference_answer, maximum=4_000)
            scoring_points = tuple(
                _visible(item, maximum=500) for item in question.scoring_points
            )
        normalized.append(
            QuestionDraft(
                logical_id=logical_id,
                ordinal=question.ordinal,
                question_type=question_type,
                stem_markdown=stem,
                options=options,
                correct_option_ids=correct_ids,
                boolean_answer=boolean_answer,
                reference_answer=reference_answer,
                scoring_points=scoring_points,
                explanation_markdown=explanation,
                knowledge_point_ids=point_ids,
            )
        )
    return tuple(normalized)


def validate_publication(
    publication: QuestionBankPublicationDraft,
    *,
    allowed_types: tuple[str, ...],
    maximum_questions: int,
    allow_empty_questions: bool = False,
) -> ValidatedPublication:
    minimum_points = 0 if allow_empty_questions else 1
    minimum_volumes = 0 if allow_empty_questions else 1
    volume_numbers = (
        tuple(volume.volume_number for volume in publication.volumes)
        if isinstance(publication, QuestionBankPublicationDraft)
        else ()
    )
    if (
        not isinstance(publication, QuestionBankPublicationDraft)
        or not isinstance(publication.knowledge_points, tuple)
        or not minimum_points <= len(publication.knowledge_points) <= 4_000
        or not isinstance(publication.volumes, tuple)
        or not minimum_volumes <= len(publication.volumes) <= 2
        or (
            not allow_empty_questions
            and volume_numbers != tuple(range(1, len(publication.volumes) + 1))
        )
    ):
        raise _invalid()
    points = tuple(
        KnowledgePointDraft(
            _identifier(point.logical_id),
            _visible(point.title, maximum=300),
            point.importance,
            tuple(_identifier(item) for item in point.source_unit_ids),
        )
        if isinstance(point, KnowledgePointDraft)
        and isinstance(point.importance, int)
        and not isinstance(point.importance, bool)
        and 1 <= point.importance <= 100
        else (_ for _ in ()).throw(_invalid())
        for point in publication.knowledge_points
    )
    point_ids = frozenset(point.logical_id for point in points)
    if len(point_ids) != len(points):
        raise _invalid()
    omitted = tuple(
        dict.fromkeys(
            _identifier(item) for item in publication.omitted_knowledge_point_ids
        )
    )
    if not set(omitted) <= point_ids:
        raise _invalid()
    volumes = tuple(
        VolumeDraft(
            volume.volume_number,
            validate_questions(
                volume.questions,
                allowed_types=allowed_types,
                knowledge_point_ids=point_ids,
                maximum_questions=maximum_questions,
                allow_noncontiguous_ordinals=allow_empty_questions,
            ),
        )
        if isinstance(volume, VolumeDraft)
        else (_ for _ in ()).throw(_invalid())
        for volume in publication.volumes
    )
    all_questions = tuple(
        question for volume in volumes for question in volume.questions
    )
    if len({question.logical_id for question in all_questions}) != len(all_questions):
        raise _invalid()
    covered = set(
        point_id
        for question in all_questions
        for point_id in question.knowledge_point_ids
    )
    if covered & set(omitted):
        raise _invalid()
    if allow_empty_questions:
        omitted = tuple(
            dict.fromkeys(
                (
                    *omitted,
                    *(point_id for point_id in point_ids if point_id not in covered),
                )
            )
        )
    elif covered | set(omitted) != point_ids:
        raise _invalid()
    tag_names = tuple(
        dict.fromkeys(_visible(value, maximum=80) for value in publication.tag_names)
    )
    if not 1 <= len(tag_names) <= 20:
        raise _invalid()
    encoded = json.dumps(
        asdict(QuestionBankPublicationDraft(points, volumes, omitted, tag_names)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(encoded) > MAX_BANK_PAYLOAD_BYTES:
        raise _invalid()
    return ValidatedPublication(
        knowledge_points=points,
        volumes=volumes,
        omitted_knowledge_point_ids=omitted,
        tag_names=tag_names,
        coverage_state=(
            QuestionBankCoverageState.PARTIAL
            if omitted
            else QuestionBankCoverageState.COMPLETE
        ),
        covered_count=len(covered),
        omitted_count=len(omitted),
    )


def question_digest(question: QuestionDraft) -> str:
    encoded = json.dumps(
        asdict(question),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(encoded).hexdigest()


def revision_digest(questions: tuple[QuestionDraft, ...]) -> str:
    encoded = json.dumps(
        [asdict(question) for question in questions],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(encoded).hexdigest()


__all__ = [
    "ValidatedPublication",
    "question_digest",
    "revision_digest",
    "validate_publication",
    "validate_questions",
]
