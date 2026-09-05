from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.utils import timezone

from apps.accounts.public import is_active_account
from apps.core.pagination import page_window
from apps.learning.contracts import (
    LearningCommandError,
    QuestionType,
    QuizAttemptStatus,
)
from apps.learning.models import QuestionBank, QuizAttempt, WrongQuestion


@dataclass(frozen=True, slots=True)
class QuizQuestionTypeOption:
    value: str
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class QuizConfiguration:
    bank_id: UUID
    revision_id: UUID
    bank_row_version: int
    title: str
    description: str
    question_count: int
    question_types: tuple[QuizQuestionTypeOption, ...]


@dataclass(frozen=True, slots=True)
class WrongQuestionQuizConfiguration(QuizConfiguration):
    source_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QuizResponseView:
    response_id: UUID
    logical_id: str
    position: int
    question_type: str
    stem_markdown: str
    options: tuple[dict[str, str], ...]
    answer: object
    self_assessment: str | None
    row_version: int
    saved_at: datetime | None
    submitted_at: datetime | None
    is_correct: bool | None
    score: int | None
    correct_option_ids: tuple[str, ...] | None
    boolean_answer: bool | None
    reference_answer: str | None
    scoring_points: tuple[str, ...] | None
    explanation_markdown: str | None


@dataclass(frozen=True, slots=True)
class QuizAttemptDetail:
    attempt_id: UUID
    source: str
    status: str
    bank_id: UUID | None
    bank_id_snapshot: UUID
    series_id_snapshot: UUID
    revision_id_snapshot: UUID
    title: str
    owner_display_name: str
    question_count: int
    answered_count: int
    selected_question_types: tuple[str, ...]
    timed: bool
    duration_minutes: int | None
    started_at: datetime
    deadline_at: datetime | None
    submitted_at: datetime | None
    actual_duration_seconds: int | None
    soft_time_exceeded: bool
    objective_score: int | None
    objective_total: int | None
    short_answer_mastered: int | None
    short_answer_total: int | None
    row_version: int
    responses: tuple[QuizResponseView, ...]


@dataclass(frozen=True, slots=True)
class QuizAttemptListItem:
    attempt_id: UUID
    title: str
    source: str
    status: str
    started_at: datetime
    deadline_at: datetime | None
    question_count: int
    row_version: int


@dataclass(frozen=True, slots=True)
class QuizAttemptPage:
    items: tuple[QuizAttemptListItem, ...]
    page_number: int
    total_pages: int
    total_items: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


def _owner(account_id) -> UUID:
    if not isinstance(account_id, UUID) or not is_active_account(account_id):
        raise LearningCommandError("learning.quiz_login_required.v1", "请先登录。")
    return account_id


def _bank(bank_id):
    try:
        bank = QuestionBank.objects.select_related(
            "series__owner", "current_revision"
        ).get(pk=bank_id, visibility="PUBLISHED")
    except (QuestionBank.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.bank_not_public.v1", "题库暂不可用。"
        ) from None
    if bank.current_revision is None:
        raise LearningCommandError("learning.bank_not_public.v1", "题库暂不可用。")
    return bank


def _type_options(revision, *, counts=None):
    values = (
        (QuestionType.SINGLE_CHOICE, "单选", revision.single_choice_count),
        (QuestionType.MULTIPLE_CHOICE, "多选", revision.multiple_choice_count),
        (QuestionType.TRUE_FALSE, "判断", revision.true_false_count),
        (QuestionType.SHORT_ANSWER, "简答", revision.short_answer_count),
    )
    if counts is not None:
        values = tuple(
            (value, label, counts.get(value, 0)) for value, label, _ in values
        )
    return tuple(
        QuizQuestionTypeOption(value, label, count)
        for value, label, count in values
        if count
    )


def quiz_configuration(*, account_id, bank_id) -> QuizConfiguration:
    _owner(account_id)
    bank = _bank(bank_id)
    revision = bank.current_revision
    return QuizConfiguration(
        bank.id,
        revision.id,
        bank.row_version,
        bank.series.base_title,
        bank.series.description,
        revision.question_count,
        _type_options(revision),
    )


def wrong_question_quiz_configuration(
    *, account_id, bank_id
) -> WrongQuestionQuizConfiguration:
    account_id = _owner(account_id)
    bank = _bank(bank_id)
    revision = bank.current_revision
    items = tuple(
        WrongQuestion.objects.filter(
            account_id=account_id,
            bank_id=bank.id,
            mastery_status="TO_REVIEW",
            question_id__isnull=False,
        ).order_by("source_key")
    )
    counts = {}
    for item in items:
        counts[item.question_type] = counts.get(item.question_type, 0) + 1
    return WrongQuestionQuizConfiguration(
        bank.id,
        revision.id,
        bank.row_version,
        bank.series.base_title,
        bank.series.description,
        len(items),
        _type_options(revision, counts=counts),
        tuple(item.source_key for item in items),
    )


def quiz_attempt_detail(
    *, account_id, attempt_id, now: datetime | None = None
) -> QuizAttemptDetail:
    account_id = _owner(account_id)
    try:
        attempt = QuizAttempt.objects.prefetch_related("responses").get(
            pk=attempt_id,
            account_id=account_id,
        )
    except (QuizAttempt.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.quiz_not_found.v1", "答题记录不存在。"
        ) from None
    submitted = attempt.status == QuizAttemptStatus.SUBMITTED
    by_logical_id = {item.logical_id: item for item in attempt.responses.all()}
    ordered = tuple(
        by_logical_id[logical_id]
        for logical_id in attempt.question_order
        if logical_id in by_logical_id
    )
    responses = tuple(
        QuizResponseView(
            response.id,
            response.logical_id,
            position,
            response.question_type,
            response.stem_markdown,
            tuple(response.options),
            response.answer,
            response.self_assessment,
            response.row_version,
            response.saved_at,
            response.submitted_at,
            response.is_correct,
            response.score,
            tuple(response.correct_option_ids) if submitted else None,
            response.boolean_answer if submitted else None,
            response.reference_answer if submitted else None,
            tuple(response.scoring_points) if submitted else None,
            response.explanation_markdown if submitted else None,
        )
        for position, response in enumerate(ordered, start=1)
    )
    answered_count = sum(
        1
        for response in ordered
        if (
            response.answer is not None
            and (not isinstance(response.answer, str) or bool(response.answer.strip()))
            and (
                not isinstance(response.answer, (list, tuple, dict))
                or bool(response.answer)
            )
        )
    )
    current = now or timezone.now()
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise LearningCommandError("learning.quiz_time_invalid.v1", "答题时间不合法。")
    return QuizAttemptDetail(
        attempt.id,
        attempt.source,
        attempt.status,
        attempt.bank_id,
        attempt.bank_id_snapshot,
        attempt.series_id_snapshot,
        attempt.revision_id_snapshot,
        attempt.bank_title,
        attempt.owner_display_name,
        attempt.question_count,
        answered_count,
        tuple(attempt.selected_question_types),
        attempt.timed,
        attempt.duration_minutes,
        attempt.started_at,
        attempt.deadline_at,
        attempt.submitted_at,
        attempt.actual_duration_seconds,
        bool(attempt.deadline_at and current >= attempt.deadline_at),
        attempt.objective_score,
        attempt.objective_total,
        attempt.short_answer_mastered,
        attempt.short_answer_total,
        attempt.row_version,
        responses,
    )


def in_progress_quiz_attempt_page(
    *, account_id, page: int = 1, page_size: int = 20
) -> QuizAttemptPage:
    account_id = _owner(account_id)
    if page_size not in {20, 50} or isinstance(page_size, bool):
        raise LearningCommandError(
            "learning.quiz_page_invalid.v1", "答题记录分页不合法。"
        )
    paginator = Paginator(
        QuizAttempt.objects.filter(
            account_id=account_id,
            status=QuizAttemptStatus.IN_PROGRESS,
        ).order_by("-started_at", "-id"),
        page_size,
    )
    selected = paginator.get_page(page)
    return QuizAttemptPage(
        tuple(
            QuizAttemptListItem(
                item.id,
                item.bank_title,
                item.source,
                item.status,
                item.started_at,
                item.deadline_at,
                item.question_count,
                item.row_version,
            )
            for item in selected.object_list
        ),
        selected.number,
        paginator.num_pages,
        paginator.count,
        selected.has_previous(),
        selected.has_next(),
    )


__all__ = [
    "QuizAttemptDetail",
    "QuizAttemptListItem",
    "QuizAttemptPage",
    "QuizConfiguration",
    "QuizQuestionTypeOption",
    "QuizResponseView",
    "WrongQuestionQuizConfiguration",
    "in_progress_quiz_attempt_page",
    "quiz_attempt_detail",
    "quiz_configuration",
    "wrong_question_quiz_configuration",
]
