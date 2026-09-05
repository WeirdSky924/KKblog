import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID

from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.accounts.public import (
    PublicAccountIdentity,
    PublicAccountNotFound,
    public_account_identities,
    public_account_identity,
)
from apps.core.pagination import page_window
from apps.learning.contracts import QuestionType
from apps.learning.models import (
    Question,
    QuestionBank,
    QuestionBankTagAssignment,
)

MIN_PUBLIC_PAGE_SIZE = 1
MAX_PUBLIC_PAGE_SIZE = 100
_SEARCH_THRESHOLD = 0.2


class PublicQuestionBankSort(StrEnum):
    LATEST = "latest"
    MOST_COMPLETED = "most_completed"
    QUESTION_COUNT_DESC = "question_count_desc"
    QUESTION_COUNT_ASC = "question_count_asc"


class QuestionBankNotFound(LookupError):
    pass


class PublicQuestionBankFilterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PublicQuestionBankFilters:
    tag_ids: tuple[UUID, ...] = ()
    question_types: tuple[str, ...] = ()
    min_questions: int | None = None
    max_questions: int | None = None
    published_from: date | None = None
    published_to: date | None = None
    author_id: UUID | None = None
    query: str = ""
    sort: PublicQuestionBankSort | str = PublicQuestionBankSort.LATEST
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class PublicQuestionBankTag:
    tag_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class PublicQuestionBankItem:
    bank_id: UUID
    series_id: UUID
    title: str
    description: str
    volume_number: int
    volume_count: int
    author: PublicAccountIdentity
    visibility: str
    question_count: int
    question_types: tuple[str, ...]
    tags: tuple[PublicQuestionBankTag, ...]
    coverage_state: str
    total_knowledge_points: int
    covered_knowledge_points: int
    omitted_knowledge_points: int
    completed_attempt_count: int
    published_at: datetime


@dataclass(frozen=True, slots=True)
class PublicQuestionBankPage:
    items: tuple[PublicQuestionBankItem, ...]
    filters: PublicQuestionBankFilters
    page_number: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


@dataclass(frozen=True, slots=True)
class PublicQuestionBankFilterOptions:
    tags: tuple[PublicQuestionBankTag, ...]
    authors: tuple[PublicAccountIdentity, ...]


@dataclass(frozen=True, slots=True)
class PublicQuestionOption:
    option_id: str
    text: str


@dataclass(frozen=True, slots=True)
class PublicQuestion:
    logical_id: str
    ordinal: int
    question_type: str
    stem_markdown: str
    options: tuple[PublicQuestionOption, ...]
    correct_option_ids: tuple[str, ...]
    boolean_answer: bool | None
    reference_answer: str
    scoring_points: tuple[str, ...]
    explanation_markdown: str


@dataclass(frozen=True, slots=True)
class PublicQuestionBankDetail:
    bank_id: UUID
    series_id: UUID
    revision_id: UUID
    title: str
    description: str
    volume_number: int
    volume_count: int
    author: PublicAccountIdentity
    question_count: int
    question_types: tuple[str, ...]
    tags: tuple[PublicQuestionBankTag, ...]
    coverage_state: str
    total_knowledge_points: int
    covered_knowledge_points: int
    omitted_knowledge_points: int
    completed_attempt_count: int
    published_at: datetime
    questions: tuple[PublicQuestion, ...]


def _integer(value, *, minimum: int, maximum: int, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise PublicQuestionBankFilterError(f"{name} is invalid")
    return value


def _validated_filters(value: PublicQuestionBankFilters) -> PublicQuestionBankFilters:
    if not isinstance(value, PublicQuestionBankFilters):
        raise PublicQuestionBankFilterError("filters are invalid")
    if (
        not isinstance(value.tag_ids, tuple)
        or len(value.tag_ids) > 20
        or any(not isinstance(item, UUID) for item in value.tag_ids)
        or not isinstance(value.question_types, tuple)
        or len(value.question_types) > len(QuestionType.values)
    ):
        raise PublicQuestionBankFilterError("filter groups are invalid")
    try:
        question_types = tuple(
            dict.fromkeys(QuestionType(item).value for item in value.question_types)
        )
        sort = PublicQuestionBankSort(value.sort)
    except (TypeError, ValueError):
        raise PublicQuestionBankFilterError("filter option is invalid") from None
    tag_ids = tuple(dict.fromkeys(value.tag_ids))
    minimum = (
        None
        if value.min_questions is None
        else _integer(value.min_questions, minimum=1, maximum=2_000, name="minimum")
    )
    maximum = (
        None
        if value.max_questions is None
        else _integer(value.max_questions, minimum=1, maximum=2_000, name="maximum")
    )
    if minimum is not None and maximum is not None and minimum > maximum:
        raise PublicQuestionBankFilterError("question range is invalid")
    if value.published_from is not None and not isinstance(value.published_from, date):
        raise PublicQuestionBankFilterError("published range is invalid")
    if value.published_to is not None and not isinstance(value.published_to, date):
        raise PublicQuestionBankFilterError("published range is invalid")
    if (
        value.published_from is not None
        and value.published_to is not None
        and (
            value.published_from > value.published_to
            or value.published_to - value.published_from > timedelta(days=3_653)
        )
    ):
        raise PublicQuestionBankFilterError("published range is invalid")
    if value.author_id is not None and not isinstance(value.author_id, UUID):
        raise PublicQuestionBankFilterError("author is invalid")
    if not isinstance(value.query, str):
        raise PublicQuestionBankFilterError("query is invalid")
    query = unicodedata.normalize("NFKC", value.query).strip()
    if len(query) > 100:
        raise PublicQuestionBankFilterError("query is invalid")
    page = _integer(value.page, minimum=1, maximum=1_000_000, name="page")
    if (
        isinstance(value.page_size, bool)
        or not isinstance(value.page_size, int)
        or not MIN_PUBLIC_PAGE_SIZE <= value.page_size <= MAX_PUBLIC_PAGE_SIZE
    ):
        raise PublicQuestionBankFilterError("page size is invalid")
    return PublicQuestionBankFilters(
        tag_ids=tag_ids,
        question_types=question_types,
        min_questions=minimum,
        max_questions=maximum,
        published_from=value.published_from,
        published_to=value.published_to,
        author_id=value.author_id,
        query=query,
        sort=sort,
        page=page,
        page_size=value.page_size,
    )


def _public_banks():
    return QuestionBank.objects.filter(
        visibility="PUBLISHED",
        current_revision__isnull=False,
        first_published_at__isnull=False,
        series__state="PUBLISHED",
        series__owner__status="ACTIVE",
    )


def _question_types(revision) -> tuple[str, ...]:
    counts = (
        (QuestionType.SINGLE_CHOICE, revision.single_choice_count),
        (QuestionType.MULTIPLE_CHOICE, revision.multiple_choice_count),
        (QuestionType.TRUE_FALSE, revision.true_false_count),
        (QuestionType.SHORT_ANSWER, revision.short_answer_count),
    )
    return tuple(question_type for question_type, count in counts if count)


def _title(bank: QuestionBank, volume_count: int) -> str:
    if volume_count == 1:
        return bank.series.base_title
    suffix = "第一卷" if bank.volume_number == 1 else "第二卷"
    return f"{bank.series.base_title} · {suffix}"


def _date_boundary(value: date, *, next_day: bool) -> datetime:
    target = value + timedelta(days=1) if next_day else value
    return timezone.make_aware(
        datetime.combine(target, time.min),
        timezone.get_current_timezone(),
    )


def _filtered_banks(filters: PublicQuestionBankFilters):
    queryset = _public_banks()
    if filters.tag_ids:
        tag_match = QuestionBankTagAssignment.objects.filter(
            series_id=OuterRef("series_id"),
            tag_id__in=filters.tag_ids,
            tag__status="ACTIVE",
        )
        queryset = queryset.annotate(selected_tag_match=Exists(tag_match)).filter(
            selected_tag_match=True
        )
    if filters.question_types:
        type_query = Q()
        fields = {
            QuestionType.SINGLE_CHOICE: "single_choice_count",
            QuestionType.MULTIPLE_CHOICE: "multiple_choice_count",
            QuestionType.TRUE_FALSE: "true_false_count",
            QuestionType.SHORT_ANSWER: "short_answer_count",
        }
        for question_type in filters.question_types:
            type_query |= Q(**{f"current_revision__{fields[question_type]}__gt": 0})
        queryset = queryset.filter(type_query)
    if filters.min_questions is not None:
        queryset = queryset.filter(
            current_revision__question_count__gte=filters.min_questions
        )
    if filters.max_questions is not None:
        queryset = queryset.filter(
            current_revision__question_count__lte=filters.max_questions
        )
    if filters.published_from is not None:
        queryset = queryset.filter(
            first_published_at__gte=_date_boundary(
                filters.published_from,
                next_day=False,
            )
        )
    if filters.published_to is not None:
        queryset = queryset.filter(
            first_published_at__lt=_date_boundary(
                filters.published_to,
                next_day=True,
            )
        )
    if filters.author_id is not None:
        queryset = queryset.filter(series__owner_id=filters.author_id)
    if filters.query:
        tag_search = (
            QuestionBankTagAssignment.objects.filter(
                series_id=OuterRef("series_id"),
                tag__status="ACTIVE",
            )
            .annotate(
                tag_similarity=TrigramSimilarity(
                    "tag__display_name",
                    filters.query,
                )
            )
            .filter(
                Q(tag__display_name__icontains=filters.query)
                | Q(tag_similarity__gte=_SEARCH_THRESHOLD)
            )
        )
        queryset = queryset.annotate(
            title_similarity=TrigramSimilarity("series__base_title", filters.query),
            description_similarity=TrigramSimilarity(
                "series__description", filters.query
            ),
            tag_search_match=Exists(tag_search),
        ).annotate(relevance=Greatest("title_similarity", "description_similarity"))
        queryset = queryset.filter(
            Q(series__base_title__icontains=filters.query)
            | Q(series__description__icontains=filters.query)
            | Q(relevance__gte=_SEARCH_THRESHOLD)
            | Q(tag_search_match=True)
        )
    return queryset


def _ordered_banks(filters: PublicQuestionBankFilters):
    queryset = _filtered_banks(filters).annotate(
        public_volume_count=Count("series__banks", distinct=True)
    )
    if filters.sort == PublicQuestionBankSort.MOST_COMPLETED:
        return queryset.order_by(
            "-completed_attempt_count",
            "-first_published_at",
            "-id",
        )
    if filters.sort == PublicQuestionBankSort.QUESTION_COUNT_DESC:
        return queryset.order_by(
            "-current_revision__question_count",
            "-first_published_at",
            "-id",
        )
    if filters.sort == PublicQuestionBankSort.QUESTION_COUNT_ASC:
        return queryset.order_by(
            "current_revision__question_count",
            "-first_published_at",
            "-id",
        )
    if filters.query:
        return queryset.order_by("-relevance", "-first_published_at", "-id")
    return queryset.order_by("-first_published_at", "-id")


def _tag_prefetch() -> Prefetch:
    return Prefetch(
        "series__tag_assignments",
        queryset=QuestionBankTagAssignment.objects.select_related("tag")
        .filter(tag__status="ACTIVE")
        .order_by("tag__normalized_name", "tag_id"),
        to_attr="public_tag_assignments",
    )


def _tags(bank: QuestionBank) -> tuple[PublicQuestionBankTag, ...]:
    return tuple(
        PublicQuestionBankTag(assignment.tag_id, assignment.tag.display_name)
        for assignment in getattr(bank.series, "public_tag_assignments", ())
    )


def _item(
    bank: QuestionBank,
    *,
    authors: dict[UUID, PublicAccountIdentity],
) -> PublicQuestionBankItem:
    revision = bank.current_revision
    assert revision is not None and bank.first_published_at is not None
    volume_count = bank.public_volume_count
    return PublicQuestionBankItem(
        bank_id=bank.id,
        series_id=bank.series_id,
        title=_title(bank, volume_count),
        description=bank.series.description,
        volume_number=bank.volume_number,
        volume_count=volume_count,
        author=authors[bank.series.owner_id],
        visibility=bank.visibility,
        question_count=revision.question_count,
        question_types=_question_types(revision),
        tags=_tags(bank),
        coverage_state=bank.series.coverage_state,
        total_knowledge_points=bank.series.total_knowledge_points,
        covered_knowledge_points=bank.series.covered_knowledge_points,
        omitted_knowledge_points=bank.series.omitted_knowledge_points,
        completed_attempt_count=bank.completed_attempt_count,
        published_at=bank.first_published_at,
    )


def public_question_bank_page(
    *,
    filters: PublicQuestionBankFilters,
) -> PublicQuestionBankPage:
    normalized = _validated_filters(filters)
    queryset = (
        _ordered_banks(normalized)
        .select_related("series__owner", "current_revision")
        .prefetch_related(_tag_prefetch())
    )
    paginator = Paginator(queryset, normalized.page_size)
    selected = paginator.get_page(normalized.page)
    banks = tuple(selected.object_list)
    authors = {
        identity.account_id: identity
        for identity in public_account_identities(
            tuple(dict.fromkeys(bank.series.owner_id for bank in banks))
        )
    }
    return PublicQuestionBankPage(
        items=tuple(_item(bank, authors=authors) for bank in banks),
        filters=normalized,
        page_number=selected.number,
        page_size=normalized.page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def public_question_bank_detail(*, bank_id: UUID) -> PublicQuestionBankDetail:
    if not isinstance(bank_id, UUID):
        raise QuestionBankNotFound("Question bank does not exist")
    try:
        bank = (
            _public_banks()
            .annotate(public_volume_count=Count("series__banks", distinct=True))
            .select_related("series__owner", "current_revision")
            .prefetch_related(_tag_prefetch())
            .get(pk=bank_id)
        )
    except QuestionBank.DoesNotExist:
        raise QuestionBankNotFound("Question bank does not exist") from None
    revision = bank.current_revision
    assert revision is not None and bank.first_published_at is not None
    try:
        author = public_account_identity(bank.series.owner_id)
    except PublicAccountNotFound:
        raise QuestionBankNotFound("Question bank does not exist") from None
    questions = tuple(
        PublicQuestion(
            logical_id=question.logical_id,
            ordinal=question.ordinal,
            question_type=question.question_type,
            stem_markdown=question.stem_markdown,
            options=tuple(
                PublicQuestionOption(option["id"], option["text"])
                for option in question.options
            ),
            correct_option_ids=tuple(question.correct_option_ids),
            boolean_answer=question.boolean_answer,
            reference_answer=question.reference_answer,
            scoring_points=tuple(question.scoring_points),
            explanation_markdown=question.explanation_markdown,
        )
        for question in Question.objects.filter(revision=revision).order_by("ordinal")
    )
    return PublicQuestionBankDetail(
        bank_id=bank.id,
        series_id=bank.series_id,
        revision_id=revision.id,
        title=_title(bank, bank.public_volume_count),
        description=bank.series.description,
        volume_number=bank.volume_number,
        volume_count=bank.public_volume_count,
        author=author,
        question_count=revision.question_count,
        question_types=_question_types(revision),
        tags=_tags(bank),
        coverage_state=bank.series.coverage_state,
        total_knowledge_points=bank.series.total_knowledge_points,
        covered_knowledge_points=bank.series.covered_knowledge_points,
        omitted_knowledge_points=bank.series.omitted_knowledge_points,
        completed_attempt_count=bank.completed_attempt_count,
        published_at=bank.first_published_at,
        questions=questions,
    )


def public_question_bank_filter_options() -> PublicQuestionBankFilterOptions:
    visible = _public_banks()
    series_ids = visible.values_list("series_id", flat=True)
    tag_rows = (
        QuestionBankTagAssignment.objects.filter(
            series_id__in=series_ids,
            tag__status="ACTIVE",
        )
        .select_related("tag")
        .order_by("tag__normalized_name", "tag_id")
        .distinct("tag__normalized_name", "tag_id")
    )
    author_ids = tuple(
        dict.fromkeys(visible.values_list("series__owner_id", flat=True))
    )
    authors = tuple(
        sorted(
            public_account_identities(author_ids),
            key=lambda item: (item.display_name.casefold(), str(item.account_id)),
        )
    )
    return PublicQuestionBankFilterOptions(
        tags=tuple(
            PublicQuestionBankTag(row.tag_id, row.tag.display_name) for row in tag_rows
        ),
        authors=authors,
    )


__all__ = [
    "PublicQuestion",
    "MAX_PUBLIC_PAGE_SIZE",
    "MIN_PUBLIC_PAGE_SIZE",
    "PublicQuestionBankDetail",
    "PublicQuestionBankFilterError",
    "PublicQuestionBankFilterOptions",
    "PublicQuestionBankFilters",
    "PublicQuestionBankItem",
    "PublicQuestionBankPage",
    "PublicQuestionBankSort",
    "PublicQuestionBankTag",
    "PublicQuestionOption",
    "QuestionBankNotFound",
    "public_question_bank_detail",
    "public_question_bank_filter_options",
    "public_question_bank_page",
]
