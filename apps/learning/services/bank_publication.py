from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.accounts.public import is_administrator
from apps.core.events import enqueue_event
from apps.learning.contracts import (
    LearningCommandError,
    QuestionBankPublicationDraft,
    QuestionBankSeriesState,
    QuestionBankVisibility,
    QuestionDraft,
    QuestionType,
)
from apps.learning.events import GENERATION_COMPLETED, GENERATION_PARTIAL
from apps.learning.models import (
    KnowledgeDocument,
    Question,
    QuestionBank,
    QuestionBankKnowledgePoint,
    QuestionBankRevision,
    QuestionBankSeries,
)
from apps.learning.policies import effective_learning_quota, locked_account_quota_state

from .bank_tags import replace_question_bank_tags
from .question_schema import (
    question_digest,
    revision_digest,
    validate_publication,
    validate_questions,
)


@dataclass(frozen=True, slots=True)
class PublishedQuestionBankSeries:
    series_id: UUID
    coverage_state: str
    volume_count: int
    covered_count: int
    omitted_count: int
    row_version: int


def _revision(
    *,
    bank: QuestionBank,
    sequence: int,
    questions: tuple[QuestionDraft, ...],
    editor_id: UUID,
    reason: str,
    total_points: int,
    omitted_ids: tuple[str, ...],
) -> QuestionBankRevision:
    type_counts = {
        QuestionType.SINGLE_CHOICE: 0,
        QuestionType.MULTIPLE_CHOICE: 0,
        QuestionType.TRUE_FALSE: 0,
        QuestionType.SHORT_ANSWER: 0,
    }
    covered = set(
        point_id for question in questions for point_id in question.knowledge_point_ids
    )
    for question in questions:
        type_counts[QuestionType(question.question_type)] += 1
    revision = QuestionBankRevision.objects.create(
        bank=bank,
        sequence=sequence,
        question_count=len(questions),
        single_choice_count=type_counts[QuestionType.SINGLE_CHOICE],
        multiple_choice_count=type_counts[QuestionType.MULTIPLE_CHOICE],
        true_false_count=type_counts[QuestionType.TRUE_FALSE],
        short_answer_count=type_counts[QuestionType.SHORT_ANSWER],
        total_knowledge_points=len(covered) + len(omitted_ids),
        covered_knowledge_points=len(covered),
        omitted_knowledge_points=len(omitted_ids),
        omitted_knowledge_point_ids=list(omitted_ids),
        editor_id=editor_id,
        reason=reason,
        content_sha256=revision_digest(questions),
    )
    for question in questions:
        Question.objects.create(
            revision=revision,
            logical_id=question.logical_id,
            ordinal=question.ordinal,
            question_type=question.question_type,
            stem_markdown=question.stem_markdown,
            options=[
                {"id": option.option_id, "text": option.text}
                for option in question.options
            ],
            correct_option_ids=list(question.correct_option_ids),
            boolean_answer=question.boolean_answer,
            reference_answer=question.reference_answer,
            scoring_points=list(question.scoring_points),
            explanation_markdown=question.explanation_markdown,
            knowledge_point_ids=list(question.knowledge_point_ids),
            validation_sha256=question_digest(question),
        )
    return revision


def publish_question_bank_generation(
    *,
    owner_id,
    series_id,
    expected_series_version: int,
    publication: QuestionBankPublicationDraft,
    now: datetime | None = None,
) -> PublishedQuestionBankSeries:
    if not isinstance(owner_id, UUID) or not isinstance(series_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库生成请求不存在。")
    current = now or timezone.now()
    if not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "题库发布时间不合法。")
    try:
        candidate = QuestionBankSeries.objects.get(pk=series_id, owner_id=owner_id)
    except QuestionBankSeries.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库生成请求不存在。"
        ) from None
    validated = validate_publication(
        publication,
        allowed_types=tuple(candidate.allowed_question_types),
        maximum_questions=candidate.max_questions_per_volume_snapshot,
    )
    with transaction.atomic():
        locked_account_quota_state(owner_id)
        series = QuestionBankSeries.objects.select_for_update().get(pk=series_id)
        try:
            KnowledgeDocument.objects.select_for_update().get(
                pk=series.source_document_id,
                owner_id=owner_id,
                state="APPROVED",
            )
        except KnowledgeDocument.DoesNotExist:
            raise LearningCommandError(
                "learning.document_not_available.v1",
                "知识文档当前不能生成题库。",
            ) from None
        if (
            series.owner_id != owner_id
            or series.row_version != expected_series_version
            or series.state
            not in {
                QuestionBankSeriesState.GENERATION_PENDING,
                QuestionBankSeriesState.GENERATING,
            }
        ):
            raise LearningCommandError(
                "learning.bank_generation_conflict.v1",
                "题库生成请求已被其他操作修改。",
            )
        additional_slots = len(validated.volumes) - series.reserved_bank_slots
        if additional_slots > 0:
            limits = effective_learning_quota(owner_id)
            reserved = (
                QuestionBankSeries.objects.filter(owner_id=owner_id)
                .exclude(
                    state__in=(
                        QuestionBankSeriesState.GENERATION_FAILED,
                        QuestionBankSeriesState.DELETED,
                    )
                )
                .aggregate(total=Sum("reserved_bank_slots", default=0))["total"]
            )
            if reserved + additional_slots > limits.unpurged_banks:
                raise LearningCommandError(
                    "learning.bank_quota_exhausted.v1",
                    "未清理题库数量不足以发布分卷。",
                )
        for point in validated.knowledge_points:
            QuestionBankKnowledgePoint.objects.create(
                series=series,
                logical_id=point.logical_id,
                title=point.title,
                importance=point.importance,
                source_unit_ids=list(point.source_unit_ids),
                omitted=point.logical_id in validated.omitted_knowledge_point_ids,
            )
        for volume in validated.volumes:
            bank = QuestionBank.objects.create(
                series=series,
                volume_number=volume.volume_number,
            )
            revision = _revision(
                bank=bank,
                sequence=1,
                questions=volume.questions,
                editor_id=owner_id,
                reason="初始生成",
                total_points=len(validated.knowledge_points),
                omitted_ids=validated.omitted_knowledge_point_ids,
            )
            bank.current_revision = revision
            bank.visibility = QuestionBankVisibility.PUBLISHED
            bank.first_published_at = current
            bank.save()
        replace_question_bank_tags(
            series=series,
            names=validated.tag_names,
            source="AGENT",
        )
        series.state = QuestionBankSeriesState.PUBLISHED
        series.coverage_state = validated.coverage_state
        series.total_knowledge_points = len(validated.knowledge_points)
        series.covered_knowledge_points = validated.covered_count
        series.omitted_knowledge_points = validated.omitted_count
        series.reserved_bank_slots = len(validated.volumes)
        series.started_at = series.started_at or current
        series.completed_at = current
        series.safe_reason_code = (
            "generation_partial"
            if validated.coverage_state == "PARTIAL"
            else "generation_complete"
        )
        series.safe_summary = (
            "题库已生成，部分知识点因单卷容量限制未覆盖。"
            if validated.coverage_state == "PARTIAL"
            else "题库已完整生成。"
        )
        series.last_error_code = ""
        series.row_version += 1
        series.save()
        enqueue_event(
            (
                GENERATION_PARTIAL
                if validated.coverage_state == "PARTIAL"
                else GENERATION_COMPLETED
            ),
            aggregate_type="question_bank_series",
            aggregate_id=str(series.id),
            payload={"recipient_id": str(series.owner_id)},
        )
    return PublishedQuestionBankSeries(
        series.id,
        series.coverage_state,
        len(validated.volumes),
        validated.covered_count,
        validated.omitted_count,
        series.row_version,
    )


def revise_question_bank(
    *,
    actor_id,
    bank_id,
    expected_bank_version: int,
    questions: tuple[QuestionDraft, ...],
    revision_reason: str,
) -> QuestionBankRevision:
    if not isinstance(actor_id, UUID) or not isinstance(bank_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    if not isinstance(revision_reason, str):
        raise LearningCommandError(
            "learning.question_schema_invalid.v1", "修订原因不合法。"
        )
    reason = " ".join(revision_reason.split())
    if not 1 <= len(reason) <= 500:
        raise LearningCommandError(
            "learning.question_schema_invalid.v1", "修订原因不合法。"
        )
    try:
        candidate = QuestionBank.objects.select_related("series").get(pk=bank_id)
    except QuestionBank.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    administrator = is_administrator(actor_id)
    if candidate.series.owner_id != actor_id and not administrator:
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    point_ids = frozenset(
        candidate.series.knowledge_points.values_list("logical_id", flat=True)
    )
    normalized = validate_questions(
        questions,
        allowed_types=tuple(candidate.series.allowed_question_types),
        knowledge_point_ids=point_ids,
        maximum_questions=candidate.series.max_questions_per_volume_snapshot,
    )
    current_questions = tuple(
        Question.objects.filter(revision_id=candidate.current_revision_id).values_list(
            "logical_id", "knowledge_point_ids"
        )
    )
    current_logical_ids = frozenset(row[0] for row in current_questions)
    current_covered_points = frozenset(
        point_id for _, covered_ids in current_questions for point_id in covered_ids
    )
    revised_logical_ids = frozenset(question.logical_id for question in normalized)
    revised_covered_points = frozenset(
        point_id for question in normalized for point_id in question.knowledge_point_ids
    )
    if (
        revised_logical_ids != current_logical_ids
        or revised_covered_points != current_covered_points
    ):
        raise LearningCommandError(
            "learning.question_schema_invalid.v1",
            "整卷修订必须保留题目身份和知识点覆盖。",
        )
    with transaction.atomic():
        bank = (
            QuestionBank.objects.select_for_update()
            .select_related("series")
            .get(pk=bank_id)
        )
        if bank.row_version != expected_bank_version or bank.visibility in {
            QuestionBankVisibility.CONFIGURING,
            QuestionBankVisibility.DELETE_PENDING,
            QuestionBankVisibility.DELETED,
        }:
            raise LearningCommandError(
                "learning.bank_conflict.v1", "题库已被其他操作修改。"
            )
        sequence = (
            bank.revisions.aggregate(maximum=Max("sequence"))["maximum"] or 0
        ) + 1
        omitted = tuple(
            bank.series.knowledge_points.filter(omitted=True).values_list(
                "logical_id", flat=True
            )
        )
        revision = _revision(
            bank=bank,
            sequence=sequence,
            questions=normalized,
            editor_id=actor_id,
            reason=reason,
            total_points=len(point_ids),
            omitted_ids=omitted,
        )
        bank.current_revision = revision
        bank.row_version += 1
        bank.save(update_fields=("current_revision", "row_version", "updated_at"))
    return revision


__all__ = [
    "PublishedQuestionBankSeries",
    "publish_question_bank_generation",
    "revise_question_bank",
]
