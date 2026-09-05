from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator

from apps.agents.public import agent_profile_available
from apps.core.pagination import PageSlice, page_window
from apps.learning.contracts import LearningCommandError
from apps.learning.generation_schema import (
    QUESTION_GENERATION_PROFILE_KEY,
    QUESTION_GENERATION_SCHEMA_KEY,
)
from apps.learning.models import (
    KnowledgeDocument,
    LearningAppeal,
    LearningQuotaPolicy,
    QuestionBank,
    QuestionBankSeries,
)

_GENERATION_FAILURE_MESSAGES = {
    "agents.quota_exhausted.v1": (
        "模型每日 token 额度不足，本次生成未继续重试；请等待下一个上海自然日，"
        "或联系管理员重置 Endpoint 今日用量后重试。"
    ),
    "agents.request_timeout.v1": "模型请求超时，本次调用失败，可稍后重新生成。",
    "agents.response_semantics_invalid.v1": "模型返回内容未通过题库规则校验，可重新生成。",
    "agents.response_schema_invalid.v1": "模型返回内容未通过题库结构校验，可重新生成。",
    "learning.question_schema_invalid.v1": "生成内容未通过题库发布校验，可重新生成。",
    "operations.task_unexpected.v1": "后台任务发生系统错误，可稍后重试；若持续失败请联系管理员。",
}


def _generation_failure_message(error_code: str) -> str:
    return _GENERATION_FAILURE_MESSAGES.get(
        error_code,
        "题库生成未完成，可稍后重试；若持续失败请联系管理员。",
    )


@dataclass(frozen=True, slots=True)
class OwnerQuestionBankVolumeItem:
    bank_id: UUID
    volume_number: int
    visibility: str
    row_version: int
    revision_id: UUID | None
    question_count: int


@dataclass(frozen=True, slots=True)
class OwnerQuestionBankSeriesItem:
    series_id: UUID
    document_id: UUID
    base_title: str
    description: str
    allowed_question_types: tuple[str, ...]
    max_questions_per_volume: int
    state: str
    coverage_state: str | None
    total_knowledge_points: int
    covered_knowledge_points: int
    omitted_knowledge_points: int
    row_version: int
    safe_summary: str | None
    failure_message: str
    tags: tuple[str, ...]
    volumes: tuple[OwnerQuestionBankVolumeItem, ...]
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class OwnerQuestionOption:
    option_id: str
    text: str


@dataclass(frozen=True, slots=True)
class OwnerQuestionItem:
    logical_id: str
    ordinal: int
    question_type: str
    stem_markdown: str
    options: tuple[OwnerQuestionOption, ...]
    correct_option_ids: tuple[str, ...]
    boolean_answer: bool | None
    reference_answer: str
    scoring_points: tuple[str, ...]
    explanation_markdown: str


@dataclass(frozen=True, slots=True)
class OwnerQuestionBankDetail:
    bank_id: UUID
    series_id: UUID
    base_title: str
    volume_number: int
    volume_count: int
    visibility: str
    row_version: int
    revision_id: UUID
    revision_sequence: int
    questions: tuple[OwnerQuestionItem, ...]


@dataclass(frozen=True, slots=True)
class OwnerQuestionBankMetadata:
    series_id: UUID
    base_title: str
    description: str
    state: str
    row_version: int
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OwnerKnowledgeDocument:
    document_id: UUID
    original_name: str | None
    title: str | None
    summary: str | None
    content_sha256: str | None
    character_count: int | None
    line_count: int | None
    estimated_tokens: int | None
    state: str
    last_reason_code: str
    safe_status_summary: str | None
    row_version: int
    failure_purge_after: datetime | None
    deletion_requested_at: datetime | None
    purge_after: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OwnerKnowledgeDocumentListItem:
    document_id: UUID
    title: str | None
    original_name: str | None
    summary: str | None
    state: str
    safe_status_summary: str | None
    character_count: int | None
    estimated_tokens: int | None
    row_version: int
    pending_appeal_id: UUID | None
    pending_appeal_version: int | None
    question_bank_series_count: int
    has_active_generation: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OwnerKnowledgeDocumentPage:
    items: tuple[OwnerKnowledgeDocumentListItem, ...]
    page_number: int
    total_pages: int
    total_items: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


def question_generation_available() -> bool:
    configured = LearningQuotaPolicy.objects.filter(
        pk=1,
        max_questions_per_volume__isnull=False,
    ).exists()
    return configured and agent_profile_available(
        profile_key=QUESTION_GENERATION_PROFILE_KEY,
        schema_key=QUESTION_GENERATION_SCHEMA_KEY,
    )


def owner_knowledge_document(
    *, owner_id: UUID, document_id: UUID
) -> OwnerKnowledgeDocument:
    if not isinstance(owner_id, UUID) or not isinstance(document_id, UUID):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    try:
        document = KnowledgeDocument.objects.get(pk=document_id, owner_id=owner_id)
    except KnowledgeDocument.DoesNotExist:
        raise LearningCommandError(
            "learning.document_not_found.v1", "知识文档不存在。"
        ) from None
    return OwnerKnowledgeDocument(
        document_id=document.id,
        original_name=document.original_name,
        title=document.title,
        summary=document.summary,
        content_sha256=document.content_sha256,
        character_count=document.character_count,
        line_count=document.line_count,
        estimated_tokens=document.estimated_tokens,
        state=document.state,
        last_reason_code=document.last_reason_code,
        safe_status_summary=document.safe_status_summary,
        row_version=document.row_version,
        failure_purge_after=document.failure_purge_after,
        deletion_requested_at=document.deletion_requested_at,
        purge_after=document.purge_after,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def owner_knowledge_document_page(
    *,
    owner_id: UUID,
    page: int = 1,
    page_size: int = 12,
) -> OwnerKnowledgeDocumentPage:
    if (
        not isinstance(owner_id, UUID)
        or isinstance(page, bool)
        or not isinstance(page, int)
        or page < 1
        or isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= 50
    ):
        raise LearningCommandError(
            "learning.document_page_invalid.v1", "知识文档页码不合法。"
        )
    paginator = Paginator(
        KnowledgeDocument.objects.filter(owner_id=owner_id)
        .exclude(state="DELETED")
        .order_by("-created_at", "-id"),
        page_size,
    )
    selected = paginator.get_page(page)
    documents = tuple(selected.object_list)
    appeals = {
        appeal.document_id: appeal
        for appeal in LearningAppeal.objects.filter(
            document_id__in=[document.id for document in documents],
            state="PENDING",
        )
    }
    series_summary_rows = (
        QuestionBankSeries.objects.filter(
            owner_id=owner_id,
            source_document_id__in=[document.id for document in documents],
        )
        .exclude(state="DELETED")
        .values("source_document_id", "state")
    )
    series_counts = Counter(row["source_document_id"] for row in series_summary_rows)
    active_generation_documents = {
        row["source_document_id"]
        for row in series_summary_rows
        if row["state"] in {"GENERATION_PENDING", "GENERATING"}
    }
    items = []
    for document in documents:
        appeal = appeals.get(document.id)
        items.append(
            OwnerKnowledgeDocumentListItem(
                document_id=document.id,
                title=document.title,
                original_name=document.original_name,
                summary=document.summary,
                state=document.state,
                safe_status_summary=document.safe_status_summary,
                character_count=document.character_count,
                estimated_tokens=document.estimated_tokens,
                row_version=document.row_version,
                pending_appeal_id=appeal.id if appeal else None,
                pending_appeal_version=appeal.row_version if appeal else None,
                question_bank_series_count=series_counts.get(document.id, 0),
                has_active_generation=document.id in active_generation_documents,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
        )
    return OwnerKnowledgeDocumentPage(
        items=tuple(items),
        page_number=selected.number,
        total_pages=paginator.num_pages,
        total_items=paginator.count,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def _owner_question_bank_series_items(
    series_rows,
) -> tuple[OwnerQuestionBankSeriesItem, ...]:
    items = []
    for series in series_rows:
        volumes = tuple(
            OwnerQuestionBankVolumeItem(
                bank_id=bank.id,
                volume_number=bank.volume_number,
                visibility=bank.visibility,
                row_version=bank.row_version,
                revision_id=bank.current_revision_id,
                question_count=(
                    bank.current_revision.question_count
                    if bank.current_revision_id
                    else 0
                ),
            )
            for bank in sorted(
                series.banks.all(), key=lambda value: value.volume_number
            )
        )
        item = OwnerQuestionBankSeriesItem(
            series_id=series.id,
            document_id=series.source_document_id,
            base_title=series.base_title,
            description=series.description,
            allowed_question_types=tuple(series.allowed_question_types),
            max_questions_per_volume=series.max_questions_per_volume_snapshot,
            state=series.state,
            coverage_state=series.coverage_state,
            total_knowledge_points=series.total_knowledge_points,
            covered_knowledge_points=series.covered_knowledge_points,
            omitted_knowledge_points=series.omitted_knowledge_points,
            row_version=series.row_version,
            safe_summary=series.safe_summary,
            failure_message=(
                _generation_failure_message(series.last_error_code)
                if series.state == "GENERATION_FAILED"
                else ""
            ),
            tags=tuple(
                assignment.tag.display_name
                for assignment in series.tag_assignments.all()
            ),
            volumes=volumes,
            created_at=series.created_at,
            completed_at=series.completed_at,
        )
        items.append(item)
    return tuple(items)


def owner_knowledge_document_question_bank_series(
    *,
    owner_id: UUID,
    document_id: UUID,
    page: int | None = None,
    page_size: int = 20,
) -> tuple[OwnerQuestionBankSeriesItem, ...] | PageSlice[OwnerQuestionBankSeriesItem]:
    """Return generation history for one owned document, independent of list paging."""
    if not isinstance(owner_id, UUID) or not isinstance(document_id, UUID):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    if not KnowledgeDocument.objects.filter(pk=document_id, owner_id=owner_id).exists():
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise LearningCommandError(
            "learning.generation_history_page_invalid.v1", "题库生成历史分页不合法。"
        )
    series_rows = (
        QuestionBankSeries.objects.filter(
            owner_id=owner_id,
            source_document_id=document_id,
        )
        .exclude(state="DELETED")
        .prefetch_related("tag_assignments__tag", "banks__current_revision")
        .order_by("-created_at", "-id")
    )
    if page is None:
        return _owner_question_bank_series_items(series_rows)
    paginator = Paginator(series_rows, page_size)
    selected = paginator.get_page(page)
    items = _owner_question_bank_series_items(selected.object_list)
    return PageSlice(
        items=items,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def owner_question_bank_metadata(
    *,
    owner_id: UUID,
    series_id: UUID,
) -> OwnerQuestionBankMetadata:
    if not isinstance(owner_id, UUID) or not isinstance(series_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    try:
        series = QuestionBankSeries.objects.prefetch_related(
            "tag_assignments__tag"
        ).get(pk=series_id, owner_id=owner_id)
    except QuestionBankSeries.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    return OwnerQuestionBankMetadata(
        series_id=series.id,
        base_title=series.base_title,
        description=series.description,
        state=series.state,
        row_version=series.row_version,
        tags=tuple(
            assignment.tag.display_name for assignment in series.tag_assignments.all()
        ),
    )


def owner_question_bank_detail(
    *,
    owner_id: UUID,
    bank_id: UUID,
) -> OwnerQuestionBankDetail:
    if not isinstance(owner_id, UUID) or not isinstance(bank_id, UUID):
        raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
    try:
        selected = QuestionBank.objects.select_related(
            "series", "current_revision"
        ).get(pk=bank_id, series__owner_id=owner_id)
    except QuestionBank.DoesNotExist:
        raise LearningCommandError(
            "learning.bank_not_found.v1", "题库不存在。"
        ) from None
    revision = selected.current_revision
    if revision is None:
        raise LearningCommandError("learning.bank_conflict.v1", "题库当前不可读取。")
    questions = tuple(
        OwnerQuestionItem(
            logical_id=question.logical_id,
            ordinal=question.ordinal,
            question_type=question.question_type,
            stem_markdown=question.stem_markdown,
            options=tuple(
                OwnerQuestionOption(option["id"], option["text"])
                for option in question.options
            ),
            correct_option_ids=tuple(question.correct_option_ids),
            boolean_answer=question.boolean_answer,
            reference_answer=question.reference_answer,
            scoring_points=tuple(question.scoring_points),
            explanation_markdown=question.explanation_markdown,
        )
        for question in revision.questions.order_by("ordinal")
    )
    return OwnerQuestionBankDetail(
        bank_id=selected.id,
        series_id=selected.series_id,
        base_title=selected.series.base_title,
        volume_number=selected.volume_number,
        volume_count=selected.series.banks.count(),
        visibility=selected.visibility,
        row_version=selected.row_version,
        revision_id=revision.id,
        revision_sequence=revision.sequence,
        questions=questions,
    )
