import unicodedata
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.accounts.public import is_active_account, is_administrator
from apps.learning.contracts import (
    GenerationQuestionTypes,
    LearningCommandError,
    QuestionBankSeriesState,
    QuestionBankVisibility,
    QuestionContentDraft,
    QuestionDraft,
    QuestionOptionDraft,
)
from apps.learning.models import Question, QuestionBank, QuestionBankSeries

from .bank_publication import revise_question_bank
from .bank_tags import replace_question_bank_tags
from .dispatch import GenerationDispatcher
from .generation_requests import (
    QuestionBankGenerationRequest,
    create_question_bank_generation_request,
)


def _text(value: object, *, maximum: int, required: bool) -> str:
    if not isinstance(value, str):
        raise LearningCommandError(
            "learning.bank_configuration_invalid.v1", "题库资料不合法。"
        )
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
        raise LearningCommandError(
            "learning.bank_configuration_invalid.v1", "题库资料不合法。"
        )
    return normalized


def _series_actor(actor_id, series_id) -> tuple[QuestionBankSeries, bool]:
    if not isinstance(actor_id, UUID) or not isinstance(series_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    try:
        series = QuestionBankSeries.objects.get(pk=series_id)
    except QuestionBankSeries.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    administrator = is_administrator(actor_id)
    if not administrator and not (
        series.owner_id == actor_id and is_active_account(actor_id)
    ):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    return series, administrator


def update_question_bank_series_metadata(
    *,
    actor_id,
    series_id,
    expected_version: int,
    base_title: str,
    description: str,
    tag_names: tuple[str, ...],
) -> QuestionBankSeries:
    candidate, administrator = _series_actor(actor_id, series_id)
    title = _text(base_title, maximum=160, required=True)
    safe_description = _text(description, maximum=1_000, required=False)
    with transaction.atomic():
        series = QuestionBankSeries.objects.select_for_update().get(pk=candidate.id)
        if (
            series.row_version != expected_version
            or series.state != QuestionBankSeriesState.PUBLISHED
            or series.banks.filter(
                visibility__in=(
                    QuestionBankVisibility.DELETE_PENDING,
                    QuestionBankVisibility.DELETED,
                )
            ).exists()
        ):
            raise LearningCommandError(
                "learning.bank_conflict.v1", "题库已被其他操作修改。"
            )
        replace_question_bank_tags(
            series=series,
            names=tag_names,
            source="ADMINISTRATOR" if administrator else "OWNER",
        )
        series.base_title = title
        series.description = safe_description
        series.row_version += 1
        series.save(
            update_fields=(
                "base_title",
                "description",
                "row_version",
                "updated_at",
            )
        )
    return series


def _question_draft(question: Question) -> QuestionDraft:
    return QuestionDraft(
        logical_id=question.logical_id,
        ordinal=question.ordinal,
        question_type=question.question_type,
        stem_markdown=question.stem_markdown,
        options=tuple(
            QuestionOptionDraft(option["id"], option["text"])
            for option in question.options
        ),
        correct_option_ids=tuple(question.correct_option_ids),
        boolean_answer=question.boolean_answer,
        reference_answer=question.reference_answer,
        scoring_points=tuple(question.scoring_points),
        explanation_markdown=question.explanation_markdown,
        knowledge_point_ids=tuple(question.knowledge_point_ids),
    )


def revise_question_in_bank(
    *,
    actor_id,
    bank_id,
    expected_bank_version: int,
    question: QuestionContentDraft,
    revision_reason: str,
):
    if not isinstance(question, QuestionContentDraft):
        raise LearningCommandError(
            "learning.question_schema_invalid.v1", "题目内容不合法。"
        )
    try:
        bank = QuestionBank.objects.select_related("series", "current_revision").get(
            pk=bank_id
        )
    except (QuestionBank.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    if not is_administrator(actor_id) and not (
        bank.series.owner_id == actor_id and is_active_account(actor_id)
    ):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    if bank.current_revision_id is None:
        raise LearningCommandError("learning.bank_conflict.v1", "题库当前不可编辑。")
    current = tuple(
        Question.objects.filter(revision_id=bank.current_revision_id).order_by(
            "ordinal"
        )
    )
    if question.logical_id not in {item.logical_id for item in current}:
        raise LearningCommandError("learning.question_not_found.v1", "题目不存在。")
    revised = []
    for item in current:
        draft = _question_draft(item)
        if item.logical_id == question.logical_id:
            draft = QuestionDraft(
                logical_id=draft.logical_id,
                ordinal=draft.ordinal,
                question_type=draft.question_type,
                stem_markdown=question.stem_markdown,
                options=question.options,
                correct_option_ids=question.correct_option_ids,
                boolean_answer=question.boolean_answer,
                reference_answer=question.reference_answer,
                scoring_points=question.scoring_points,
                explanation_markdown=question.explanation_markdown,
                knowledge_point_ids=draft.knowledge_point_ids,
            )
        revised.append(draft)
    return revise_question_bank(
        actor_id=actor_id,
        bank_id=bank.id,
        expected_bank_version=expected_bank_version,
        questions=tuple(revised),
        revision_reason=revision_reason,
    )


def retry_question_bank_generation(
    *,
    owner_id,
    series_id,
    expected_version: int,
    idempotency_key: str,
    dispatcher: GenerationDispatcher,
    now: datetime | None = None,
) -> QuestionBankGenerationRequest:
    if not isinstance(owner_id, UUID) or not isinstance(series_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    try:
        series = QuestionBankSeries.objects.get(
            pk=series_id,
            owner_id=owner_id,
            state=QuestionBankSeriesState.GENERATION_FAILED,
            row_version=expected_version,
        )
    except QuestionBankSeries.DoesNotExist:
        raise LearningCommandError(
            "learning.generation_retry_conflict.v1", "题库生成当前不能重试。"
        ) from None
    allowed = set(series.allowed_question_types)
    return create_question_bank_generation_request(
        owner_id=owner_id,
        document_id=series.source_document_id,
        base_title=series.base_title,
        description=series.description,
        question_types=GenerationQuestionTypes(
            single_choice="SINGLE_CHOICE" in allowed,
            multiple_choice="MULTIPLE_CHOICE" in allowed,
            true_false="TRUE_FALSE" in allowed,
            short_answer="SHORT_ANSWER" in allowed,
        ),
        idempotency_key=idempotency_key,
        dispatcher=dispatcher,
        now=now,
    )


__all__ = [
    "retry_question_bank_generation",
    "revise_question_in_bank",
    "update_question_bank_series_metadata",
]
