from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.public import is_administrator
from apps.core.pagination import PageSlice, page_window
from apps.learning.contracts import (
    KnowledgeDocumentState,
    LearningAdminTargetType,
    LearningAppealState,
    LearningCommandError,
    QuestionBankVisibility,
)
from apps.learning.models import (
    KnowledgeDocument,
    KnowledgeDocumentAccess,
    LearningAccountQuotaOverride,
    LearningAppeal,
    LearningQuotaPolicy,
    QuestionBank,
)

ADMIN_LEARNING_PAGE_SIZES = frozenset({20, 50})


def _administrator(value) -> UUID:
    if not isinstance(value, UUID) or not is_administrator(value):
        raise PermissionError("Administrator access required")
    return value


def _page(value, page_size: int) -> int:
    if isinstance(page_size, bool) or page_size not in ADMIN_LEARNING_PAGE_SIZES:
        raise LearningCommandError(
            "learning.administration_page_invalid.v1", "管理页面分页不合法。"
        )
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


@dataclass(frozen=True, slots=True)
class AdminLearningDocumentItem:
    document_id: UUID
    owner_id: UUID
    owner_display_name: str
    owner_email: str
    title: str | None
    original_name: str | None
    state: str
    safe_status_summary: str | None
    last_reason_code: str
    admin_lock_reason: str
    admin_hidden_at: datetime | None
    deletion_actor: str
    row_version: int
    pending_appeal_id: UUID | None
    pending_appeal_version: int | None
    character_count: int | None
    estimated_tokens: int | None
    created_at: datetime
    updated_at: datetime

    @property
    def admin_hidden(self) -> bool:
        return self.admin_hidden_at is not None


@dataclass(frozen=True, slots=True)
class AdminLearningDocumentPage:
    items: tuple[AdminLearningDocumentItem, ...]
    keyword: str
    state: str
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
class AdminKnowledgeAccessItem:
    actor_id: UUID
    actor_display_name: str
    purpose: str
    accessed_at: datetime
    trace_code: str


@dataclass(frozen=True, slots=True)
class AdminLearningDocumentDetail:
    item: AdminLearningDocumentItem
    access_history: tuple[AdminKnowledgeAccessItem, ...]
    access_page: PageSlice[AdminKnowledgeAccessItem] | None = None


@dataclass(frozen=True, slots=True)
class AdminQuestionBankItem:
    bank_id: UUID
    series_id: UUID
    owner_id: UUID
    owner_display_name: str
    owner_email: str
    title: str
    volume_number: int
    series_state: str
    visibility: str
    admin_lock_reason: str
    deletion_actor: str
    row_version: int
    question_count: int
    question_types: tuple[str, ...]
    safe_summary: str | None
    last_error_code: str
    coverage_state: str | None
    completed_attempt_count: int
    purge_after: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminQuestionBankPage:
    items: tuple[AdminQuestionBankItem, ...]
    keyword: str
    state: str
    visibility: str
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
class AdminLearningAppealItem:
    appeal_id: UUID
    target_type: str
    target_id: UUID
    document_id: UUID | None
    bank_id: UUID | None
    appellant_id: UUID
    appellant_display_name: str
    appellant_email: str
    state: str
    target_row_version: int
    row_version: int
    reason_markdown: str
    decision_markdown: str | None
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdminLearningAppealPage:
    items: tuple[AdminLearningAppealItem, ...]
    state: str
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
class AdminLearningQuotaSite:
    daily_uploads: int
    pending_reviews: int
    daily_generations: int
    concurrent_model_runs: int
    unpurged_banks: int
    max_questions_per_volume: int | None
    row_version: int


@dataclass(frozen=True, slots=True)
class AdminLearningQuotaOverrideItem:
    account_id: UUID
    daily_uploads: int | None
    pending_reviews: int | None
    daily_generations: int | None
    concurrent_model_runs: int | None
    unpurged_banks: int | None
    row_version: int


@dataclass(frozen=True, slots=True)
class AdminLearningQuotaSnapshot:
    site: AdminLearningQuotaSite
    overrides: tuple[AdminLearningQuotaOverrideItem, ...]
    override_page: PageSlice[AdminLearningQuotaOverrideItem] | None = None


def _document_item(document, appeal=None) -> AdminLearningDocumentItem:
    return AdminLearningDocumentItem(
        document_id=document.id,
        owner_id=document.owner_id,
        owner_display_name=document.owner.nickname
        or document.owner.email.split("@", 1)[0],
        owner_email=document.owner.email,
        title=document.title,
        original_name=document.original_name,
        state=document.state,
        safe_status_summary=document.safe_status_summary,
        last_reason_code=document.last_reason_code,
        admin_lock_reason=document.admin_lock_reason,
        admin_hidden_at=document.admin_hidden_at,
        deletion_actor=document.deletion_actor,
        row_version=document.row_version,
        pending_appeal_id=appeal.id if appeal else None,
        pending_appeal_version=appeal.row_version if appeal else None,
        character_count=document.character_count,
        estimated_tokens=document.estimated_tokens,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def admin_learning_document_page(
    *, actor_id, keyword: str = "", state: str = "", page: int = 1, page_size: int = 20
) -> AdminLearningDocumentPage:
    _administrator(actor_id)
    if not isinstance(keyword, str) or len(keyword) > 100:
        raise LearningCommandError(
            "learning.administration_filter_invalid.v1", "管理筛选条件不合法。"
        )
    state = state.strip().upper()
    if state and state not in KnowledgeDocumentState.values:
        raise LearningCommandError(
            "learning.administration_filter_invalid.v1", "文档状态筛选不合法。"
        )
    normalized_page = _page(page, page_size)
    queryset = KnowledgeDocument.objects.select_related("owner").exclude(
        state=KnowledgeDocumentState.DELETED
    )
    if state:
        queryset = queryset.filter(state=state)
    if keyword.strip():
        value = keyword.strip()
        queryset = queryset.filter(
            Q(title__icontains=value)
            | Q(original_name__icontains=value)
            | Q(owner__email__icontains=value)
            | Q(owner__nickname__icontains=value)
        )
    paginator = Paginator(queryset.order_by("-created_at", "-id"), page_size)
    selected = paginator.get_page(normalized_page)
    documents = tuple(selected.object_list)
    appeals = {
        appeal.document_id: appeal
        for appeal in LearningAppeal.objects.filter(
            document_id__in=[document.id for document in documents],
            state=LearningAppealState.PENDING,
        )
    }
    return AdminLearningDocumentPage(
        items=tuple(
            _document_item(document, appeals.get(document.id)) for document in documents
        ),
        keyword=keyword.strip(),
        state=state,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def admin_learning_document_detail(
    *, actor_id, document_id, page: int | None = None, page_size: int = 20
) -> AdminLearningDocumentDetail:
    _administrator(actor_id)
    try:
        document = KnowledgeDocument.objects.select_related("owner").get(pk=document_id)
    except (KnowledgeDocument.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.document_not_found.v1", "知识文档不存在。"
        ) from None
    appeal = LearningAppeal.objects.filter(
        document_id=document.id,
        state=LearningAppealState.PENDING,
    ).first()
    if page is not None and (
        isinstance(page, bool) or page < 1 or page_size not in (10, 20, 50)
    ):
        raise LearningCommandError(
            "learning.document_access_page_invalid.v1", "访问记录分页不合法。"
        )
    ordered = KnowledgeDocumentAccess.objects.filter(
        document_id=document.id
    ).select_related("administrator_actor").order_by("-accessed_at", "-id")

    def access_item(item) -> AdminKnowledgeAccessItem:
        return AdminKnowledgeAccessItem(
            actor_id=item.administrator_actor_id,
            actor_display_name=(
                item.administrator_actor.nickname
                or item.administrator_actor.email.split("@", 1)[0]
            ),
            purpose=item.purpose,
            accessed_at=item.accessed_at,
            trace_code=item.trace_code,
        )

    if page is None:
        history = tuple(access_item(item) for item in ordered[:100])
        access_page = None
    else:
        paginator = Paginator(ordered, page_size)
        selected = paginator.get_page(page)
        history = tuple(access_item(item) for item in selected.object_list)
        access_page = PageSlice(
            items=history,
            page_number=selected.number,
            page_size=page_size,
            total_items=paginator.count,
            total_pages=paginator.num_pages,
            has_previous=selected.has_previous(),
            has_next=selected.has_next(),
        )
    return AdminLearningDocumentDetail(
        item=_document_item(document, appeal),
        access_history=history,
        access_page=access_page,
    )


def _bank_item(bank) -> AdminQuestionBankItem:
    revision = bank.current_revision
    types = ()
    count = 0
    if revision is not None:
        count = revision.question_count
        types = tuple(
            question_type
            for question_type, value in (
                ("SINGLE_CHOICE", revision.single_choice_count),
                ("MULTIPLE_CHOICE", revision.multiple_choice_count),
                ("TRUE_FALSE", revision.true_false_count),
                ("SHORT_ANSWER", revision.short_answer_count),
            )
            if value
        )
    return AdminQuestionBankItem(
        bank_id=bank.id,
        series_id=bank.series_id,
        owner_id=bank.series.owner_id,
        owner_display_name=bank.series.owner.nickname
        or bank.series.owner.email.split("@", 1)[0],
        owner_email=bank.series.owner.email,
        title=bank.series.base_title,
        volume_number=bank.volume_number,
        series_state=bank.series.state,
        visibility=bank.visibility,
        admin_lock_reason=bank.admin_lock_reason,
        deletion_actor=bank.deletion_actor,
        row_version=bank.row_version,
        question_count=count,
        question_types=types,
        safe_summary=bank.series.safe_summary,
        last_error_code=bank.series.last_error_code,
        coverage_state=bank.series.coverage_state,
        completed_attempt_count=bank.completed_attempt_count,
        purge_after=bank.purge_after,
        created_at=bank.created_at,
        updated_at=bank.updated_at,
    )


def admin_question_bank_page(
    *,
    actor_id,
    keyword: str = "",
    state: str = "",
    visibility: str = "",
    page: int = 1,
    page_size: int = 20,
) -> AdminQuestionBankPage:
    _administrator(actor_id)
    if not isinstance(keyword, str) or len(keyword) > 100:
        raise LearningCommandError(
            "learning.administration_filter_invalid.v1", "管理筛选条件不合法。"
        )
    state = state.strip().upper()
    visibility = visibility.strip().upper()
    if state and state not in {
        "GENERATION_PENDING",
        "GENERATING",
        "PUBLISHED",
        "GENERATION_FAILED",
        "DELETED",
    }:
        raise LearningCommandError(
            "learning.administration_filter_invalid.v1", "题库运行状态筛选不合法。"
        )
    if visibility and visibility not in QuestionBankVisibility.values:
        raise LearningCommandError(
            "learning.administration_filter_invalid.v1", "题库可见性筛选不合法。"
        )
    normalized_page = _page(page, page_size)
    queryset = QuestionBank.objects.select_related(
        "series__owner", "current_revision"
    ).exclude(visibility=QuestionBankVisibility.DELETED)
    if state:
        queryset = queryset.filter(series__state=state)
    if visibility:
        queryset = queryset.filter(visibility=visibility)
    if keyword.strip():
        value = keyword.strip()
        queryset = queryset.filter(
            Q(series__base_title__icontains=value)
            | Q(series__owner__email__icontains=value)
            | Q(series__owner__nickname__icontains=value)
        )
    paginator = Paginator(queryset.order_by("-created_at", "-id"), page_size)
    selected = paginator.get_page(normalized_page)
    return AdminQuestionBankPage(
        items=tuple(_bank_item(bank) for bank in selected.object_list),
        keyword=keyword.strip(),
        state=state,
        visibility=visibility,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def _appeal_item(appeal) -> AdminLearningAppealItem:
    if appeal.document_id is not None:
        target_type = LearningAdminTargetType.DOCUMENT
        target_id = appeal.document_id
    else:
        target_type = LearningAdminTargetType.QUESTION_BANK
        target_id = appeal.question_bank_id
    return AdminLearningAppealItem(
        appeal_id=appeal.id,
        target_type=target_type,
        target_id=target_id,
        document_id=appeal.document_id,
        bank_id=appeal.question_bank_id,
        appellant_id=appeal.appellant_id,
        appellant_display_name=appeal.appellant.nickname
        or appeal.appellant.email.split("@", 1)[0],
        appellant_email=appeal.appellant.email,
        state=appeal.state,
        target_row_version=appeal.target_row_version,
        row_version=appeal.row_version,
        reason_markdown=appeal.reason_markdown,
        decision_markdown=appeal.decision_markdown,
        created_at=appeal.created_at,
        decided_at=appeal.decided_at,
    )


def admin_learning_appeal_page(
    *,
    actor_id,
    state: str = LearningAppealState.PENDING,
    page: int = 1,
    page_size: int = 20,
) -> AdminLearningAppealPage:
    _administrator(actor_id)
    state = state.strip().upper()
    if state and state not in LearningAppealState.values:
        raise LearningCommandError(
            "learning.administration_filter_invalid.v1", "申诉状态筛选不合法。"
        )
    normalized_page = _page(page, page_size)
    queryset = LearningAppeal.objects.select_related("appellant")
    if state:
        queryset = queryset.filter(state=state)
    paginator = Paginator(queryset.order_by("-created_at", "-id"), page_size)
    selected = paginator.get_page(normalized_page)
    return AdminLearningAppealPage(
        items=tuple(_appeal_item(appeal) for appeal in selected.object_list),
        state=state,
        page_number=selected.number,
        page_size=page_size,
        total_items=paginator.count,
        total_pages=paginator.num_pages,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def admin_learning_appeal_detail(*, actor_id, appeal_id) -> AdminLearningAppealItem:
    _administrator(actor_id)
    try:
        appeal = LearningAppeal.objects.select_related("appellant").get(pk=appeal_id)
    except (LearningAppeal.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.appeal_not_found.v1", "申诉不存在。"
        ) from None
    return _appeal_item(appeal)


def admin_learning_quota_snapshot(*, actor_id, page: int = 1, page_size: int = 20):
    _administrator(actor_id)
    normalized_page = _page(page, page_size)
    policy = LearningQuotaPolicy.objects.get(pk=1)
    paginator = Paginator(
        LearningAccountQuotaOverride.objects.order_by("account_id"),
        page_size,
    )
    selected = paginator.get_page(normalized_page)
    site = AdminLearningQuotaSite(
        daily_uploads=policy.daily_uploads,
        pending_reviews=policy.pending_reviews,
        daily_generations=policy.daily_generations,
        concurrent_model_runs=policy.concurrent_model_runs,
        unpurged_banks=policy.unpurged_banks,
        max_questions_per_volume=policy.max_questions_per_volume,
        row_version=policy.row_version,
    )
    overrides = tuple(
        AdminLearningQuotaOverrideItem(
            account_id=item.account_id,
            daily_uploads=item.daily_uploads,
            pending_reviews=item.pending_reviews,
            daily_generations=item.daily_generations,
            concurrent_model_runs=item.concurrent_model_runs,
            unpurged_banks=item.unpurged_banks,
            row_version=item.row_version,
        )
        for item in selected.object_list
    )
    return AdminLearningQuotaSnapshot(
        site=site,
        overrides=overrides,
        override_page=PageSlice(
            items=overrides,
            page_number=selected.number,
            page_size=page_size,
            total_items=paginator.count,
            total_pages=paginator.num_pages,
            has_previous=selected.has_previous(),
            has_next=selected.has_next(),
        ),
    )


def admin_learning_account_quota_override(*, actor_id, account_id):
    _administrator(actor_id)
    try:
        identity = UUID(str(account_id))
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.account_not_found.v1", "账户不存在。"
        ) from None
    item = LearningAccountQuotaOverride.objects.filter(account_id=identity).first()
    if item is None:
        return None
    return AdminLearningQuotaOverrideItem(
        account_id=item.account_id,
        daily_uploads=item.daily_uploads,
        pending_reviews=item.pending_reviews,
        daily_generations=item.daily_generations,
        concurrent_model_runs=item.concurrent_model_runs,
        unpurged_banks=item.unpurged_banks,
        row_version=item.row_version,
    )


__all__ = [
    "ADMIN_LEARNING_PAGE_SIZES",
    "AdminKnowledgeAccessItem",
    "AdminLearningAppealItem",
    "AdminLearningAppealPage",
    "AdminLearningDocumentDetail",
    "AdminLearningDocumentItem",
    "AdminLearningDocumentPage",
    "AdminLearningQuotaOverrideItem",
    "AdminLearningQuotaSite",
    "AdminLearningQuotaSnapshot",
    "AdminQuestionBankItem",
    "AdminQuestionBankPage",
    "admin_learning_appeal_page",
    "admin_learning_appeal_detail",
    "admin_learning_account_quota_override",
    "admin_learning_document_detail",
    "admin_learning_document_page",
    "admin_learning_quota_snapshot",
    "admin_question_bank_page",
]
