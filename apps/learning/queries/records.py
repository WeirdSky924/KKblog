import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import QuerySet

from apps.accounts.public import is_active_account
from apps.core.pagination import PageSlice, page_window
from apps.learning.contracts import (
    LearningCommandError,
    QuestionBankVisibility,
    QuestionType,
    QuizAttemptSource,
    QuizAttemptStatus,
    QuizMasteryStatus,
)
from apps.learning.models import QuestionBank, QuizAttempt, QuizResponse, WrongQuestion

from .quizzes import QuizAttemptDetail, quiz_attempt_detail

_PAGE_SIZES = frozenset({20, 50})
_QUESTION_TYPE_LABELS = {
    QuestionType.SINGLE_CHOICE: "单选",
    QuestionType.MULTIPLE_CHOICE: "多选",
    QuestionType.TRUE_FALSE: "判断",
    QuestionType.SHORT_ANSWER: "简答",
}


@dataclass(frozen=True, slots=True)
class WrongQuestionItem:
    wrong_question_id: UUID
    bank_id: UUID | None
    bank_title: str
    practice_available: bool
    question_type: str
    question_type_label: str
    stem_markdown: str
    options: tuple[dict[str, str], ...]
    wrong_count: int
    correct_count: int
    first_wrong_at: datetime
    last_wrong_at: datetime
    last_correct_at: datetime | None
    mastery_status: str
    row_version: int


@dataclass(frozen=True, slots=True)
class WrongQuestionGroup:
    group_key: str
    bank_id: UUID | None
    bank_title: str
    practice_available: bool
    item_count: int
    items: tuple[WrongQuestionItem, ...]


@dataclass(frozen=True, slots=True)
class WrongQuestionPage:
    items: tuple[WrongQuestionItem, ...]
    groups: tuple[WrongQuestionGroup, ...]
    mastery_status: str
    bank_id: UUID | None
    page_number: int
    total_pages: int
    total_items: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


@dataclass(frozen=True, slots=True)
class WrongQuestionBankOption:
    bank_id: UUID | None
    bank_title: str
    item_count: int
    practice_available: bool


@dataclass(frozen=True, slots=True)
class QuizRecordItem:
    attempt_id: UUID
    bank_id: UUID
    bank_title: str
    source: str
    source_label: str
    status: str
    status_label: str
    started_at: datetime
    submitted_at: datetime | None
    question_count: int
    objective_score: int | None
    objective_total: int | None
    short_answer_mastered: int | None
    short_answer_total: int | None
    row_version: int


@dataclass(frozen=True, slots=True)
class QuizRecordPage:
    items: tuple[QuizRecordItem, ...]
    bank_id: UUID | None
    source: str
    status: str
    page_number: int
    total_pages: int
    total_items: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


@dataclass(frozen=True, slots=True)
class QuizRecordBankOption:
    bank_id: UUID
    bank_title: str
    item_count: int


def _owner(account_id: UUID) -> UUID:
    if not isinstance(account_id, UUID) or not is_active_account(account_id):
        raise LearningCommandError("learning.quiz_login_required.v1", "请先登录。")
    return account_id


def _page_size(value: int) -> int:
    if isinstance(value, bool) or value not in _PAGE_SIZES:
        raise LearningCommandError("learning.quiz_page_invalid.v1", "分页参数不合法。")
    return value


def _uuid(value, *, code: str = "learning.quiz_filter_invalid.v1") -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise LearningCommandError(code, "筛选参数不合法。") from None


def _mastery(value: str) -> str:
    value = value.value if isinstance(value, QuizMasteryStatus) else value
    if value in {"", "ALL", None}:
        return "ALL"
    if value not in QuizMasteryStatus.values:
        raise LearningCommandError(
            "learning.quiz_filter_invalid.v1", "掌握状态不合法。"
        )
    return value


def _bank_availability(bank_ids: set[UUID]) -> dict[UUID, bool]:
    if not bank_ids:
        return {}
    return {
        bank.id: bank.visibility == QuestionBankVisibility.PUBLISHED
        for bank in QuestionBank.objects.filter(id__in=bank_ids).only(
            "id", "visibility"
        )
    }


def wrong_question_page(
    *,
    account_id,
    mastery_status: str = QuizMasteryStatus.TO_REVIEW,
    bank_id=None,
    page: int = 1,
    page_size: int = 20,
) -> WrongQuestionPage:
    account_id = _owner(account_id)
    state = _mastery(mastery_status)
    selected_bank = _uuid(bank_id)
    size = _page_size(page_size)
    queryset = WrongQuestion.objects.filter(account_id=account_id)
    if state != "ALL":
        queryset = queryset.filter(mastery_status=state)
    if selected_bank is not None:
        queryset = queryset.filter(bank_id=selected_bank)
    queryset = queryset.order_by("bank_title", "source_key", "id")
    paginator = Paginator(queryset, size)
    selected = paginator.get_page(page)
    rows = tuple(selected.object_list)
    availability = _bank_availability({item.bank_id for item in rows if item.bank_id})
    items = tuple(
        WrongQuestionItem(
            item.id,
            item.bank_id,
            item.bank_title,
            bool(item.bank_id and availability.get(item.bank_id, False)),
            item.question_type,
            _QUESTION_TYPE_LABELS.get(item.question_type, item.question_type),
            item.stem_markdown,
            tuple(item.options),
            item.wrong_count,
            item.correct_count,
            item.first_wrong_at,
            item.last_wrong_at,
            item.last_correct_at,
            item.mastery_status,
            item.row_version,
        )
        for item in rows
    )
    grouped: dict[str, list[WrongQuestionItem]] = defaultdict(list)
    for item in items:
        grouped[str(item.bank_id or f"deleted:{item.bank_title}")].append(item)
    groups = tuple(
        WrongQuestionGroup(
            key,
            values[0].bank_id,
            values[0].bank_title,
            values[0].practice_available,
            len(values),
            tuple(values),
        )
        for key, values in grouped.items()
    )
    return WrongQuestionPage(
        items,
        groups,
        state,
        selected_bank,
        selected.number,
        paginator.num_pages,
        paginator.count,
        selected.has_previous(),
        selected.has_next(),
    )


def wrong_question_bank_options(*, account_id) -> tuple[WrongQuestionBankOption, ...]:
    account_id = _owner(account_id)
    rows = (
        WrongQuestion.objects.filter(account_id=account_id)
        .values("bank_id", "bank_title")
        .order_by("bank_title", "bank_id")
    )
    counts: dict[tuple[UUID | None, str], int] = defaultdict(int)
    for row in rows:
        counts[(row["bank_id"], row["bank_title"])] += 1
    availability = _bank_availability({key[0] for key in counts if key[0]})
    return tuple(
        WrongQuestionBankOption(
            bank_id,
            title,
            count,
            bool(bank_id and availability.get(bank_id, False)),
        )
        for (bank_id, title), count in counts.items()
    )


def _record_queryset(
    *,
    account_id,
    bank_id=None,
    source: str = "",
    status: str = "",
    started_from=None,
    started_to=None,
) -> QuerySet:
    queryset = QuizAttempt.objects.filter(
        account_id=account_id,
        status__in=(QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED),
    )
    selected_bank = _uuid(bank_id)
    if selected_bank is not None:
        queryset = queryset.filter(bank_id_snapshot=selected_bank)
    if source:
        if source not in QuizAttemptSource.values:
            raise LearningCommandError(
                "learning.quiz_filter_invalid.v1", "来源筛选不合法。"
            )
        queryset = queryset.filter(source=source)
    if status:
        if status not in {QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED}:
            raise LearningCommandError(
                "learning.quiz_filter_invalid.v1", "完成状态不合法。"
            )
        queryset = queryset.filter(status=status)
    if started_from:
        queryset = queryset.filter(started_at__date__gte=started_from)
    if started_to:
        queryset = queryset.filter(started_at__date__lte=started_to)
    return queryset.order_by("-started_at", "-id")


def quiz_record_page(
    *,
    account_id,
    bank_id=None,
    source: str = "",
    status: str = "",
    started_from: date | None = None,
    started_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> QuizRecordPage:
    account_id = _owner(account_id)
    size = _page_size(page_size)
    paginator = Paginator(
        _record_queryset(
            account_id=account_id,
            bank_id=bank_id,
            source=source,
            status=status,
            started_from=started_from,
            started_to=started_to,
        ),
        size,
    )
    selected = paginator.get_page(page)
    return QuizRecordPage(
        tuple(
            QuizRecordItem(
                item.id,
                item.bank_id_snapshot,
                item.bank_title,
                item.source,
                QuizAttemptSource(item.source).label,
                item.status,
                QuizAttemptStatus(item.status).label,
                item.started_at,
                item.submitted_at,
                item.question_count,
                item.objective_score,
                item.objective_total,
                item.short_answer_mastered,
                item.short_answer_total,
                item.row_version,
            )
            for item in selected.object_list
        ),
        _uuid(bank_id),
        source,
        status,
        selected.number,
        paginator.num_pages,
        paginator.count,
        selected.has_previous(),
        selected.has_next(),
    )


def pending_quiz_records(
    *, account_id, page: int | None = None, page_size: int = 20
) -> tuple[QuizRecordItem, ...] | PageSlice[QuizRecordItem]:
    account_id = _owner(account_id)
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise LearningCommandError(
            "learning.quiz_pending_page_invalid.v1", "删除冷静期分页不合法。"
        )
    ordered = QuizAttempt.objects.filter(
        account_id=account_id, status=QuizAttemptStatus.DELETE_PENDING
    ).order_by("purge_after", "id")

    def item(value) -> QuizRecordItem:
        return QuizRecordItem(
            value.id,
            value.bank_id_snapshot,
            value.bank_title,
            value.source,
            QuizAttemptSource(value.source).label,
            value.status,
            QuizAttemptStatus(value.status).label,
            value.started_at,
            value.submitted_at,
            value.question_count,
            value.objective_score,
            value.objective_total,
            value.short_answer_mastered,
            value.short_answer_total,
            value.row_version,
        )

    if page is None:
        return tuple(item(value) for value in ordered)
    paginator = Paginator(ordered, page_size)
    selected = paginator.get_page(page)
    return PageSlice(
        items=tuple(item(value) for value in selected.object_list),
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def quiz_record_bank_options(*, account_id) -> tuple[QuizRecordBankOption, ...]:
    account_id = _owner(account_id)
    rows = (
        QuizAttempt.objects.filter(
            account_id=account_id,
            status__in=(QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED),
        )
        .values("bank_id_snapshot", "bank_title")
        .order_by("bank_title", "bank_id_snapshot")
    )
    counts: dict[tuple[UUID, str], int] = defaultdict(int)
    for row in rows:
        counts[(row["bank_id_snapshot"], row["bank_title"])] += 1
    return tuple(
        QuizRecordBankOption(bank_id, title, count)
        for (bank_id, title), count in counts.items()
    )


def quiz_record_detail(*, account_id, attempt_id) -> QuizAttemptDetail:
    account_id = _owner(account_id)
    attempt = QuizAttempt.objects.filter(
        pk=attempt_id,
        account_id=account_id,
        status__in=(QuizAttemptStatus.IN_PROGRESS, QuizAttemptStatus.SUBMITTED),
    ).exists()
    if not attempt:
        raise LearningCommandError("learning.quiz_not_found.v1", "答题记录不存在。")
    return quiz_attempt_detail(account_id=account_id, attempt_id=attempt_id)


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv_value(value: object) -> str:
    if isinstance(value, (list, tuple, dict)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return _csv_cell(value)


def iter_quiz_record_csv(
    *,
    account_id,
    bank_id=None,
    source: str = "",
    status: str = "",
    started_from=None,
    started_to=None,
):
    account_id = _owner(account_id)
    responses = (
        QuizResponse.objects.select_related("attempt")
        .filter(
            attempt__in=_record_queryset(
                account_id=account_id,
                bank_id=bank_id,
                source=source,
                status=status,
                started_from=started_from,
                started_to=started_to,
            )
        )
        .order_by("-attempt__started_at", "-attempt_id", "ordinal", "id")
        .iterator(chunk_size=200)
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        (
            "题库",
            "来源",
            "开始时间",
            "提交时间",
            "题号",
            "题型",
            "题面",
            "答案",
            "是否正确",
            "得分",
            "简答自评",
        )
    )
    yield buffer.getvalue()
    for response in responses:
        buffer.seek(0)
        buffer.truncate(0)
        attempt = response.attempt
        writer.writerow(
            (
                _csv_value(attempt.bank_title),
                _csv_value(QuizAttemptSource(attempt.source).label),
                _csv_value(attempt.started_at.isoformat()),
                _csv_value(
                    attempt.submitted_at.isoformat() if attempt.submitted_at else ""
                ),
                _csv_value(response.ordinal),
                _csv_value(
                    _QUESTION_TYPE_LABELS.get(
                        response.question_type, response.question_type
                    )
                ),
                _csv_value(response.stem_markdown),
                _csv_value(response.answer),
                _csv_value(
                    "是"
                    if response.is_correct is True
                    else "否"
                    if response.is_correct is False
                    else ""
                ),
                _csv_value(response.score),
                _csv_value(response.self_assessment),
            )
        )
        yield buffer.getvalue()


__all__ = [
    "QuizRecordBankOption",
    "QuizRecordItem",
    "QuizRecordPage",
    "WrongQuestionBankOption",
    "WrongQuestionGroup",
    "WrongQuestionItem",
    "WrongQuestionPage",
    "iter_quiz_record_csv",
    "quiz_record_detail",
    "quiz_record_bank_options",
    "quiz_record_page",
    "pending_quiz_records",
    "wrong_question_bank_options",
    "wrong_question_page",
]
