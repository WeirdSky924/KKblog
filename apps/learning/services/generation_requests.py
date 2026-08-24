import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.public import can_upload_attachments
from apps.agents.public import AgentCommandError, create_agent_invocation
from apps.learning.contracts import (
    GenerationQuestionTypes,
    KnowledgeDocumentState,
    LearningCommandError,
    QuestionBankSeriesState,
)
from apps.learning.generation_schema import QUESTION_GENERATION_PROFILE_KEY
from apps.learning.models import (
    KnowledgeDocument,
    LearningQuotaPolicy,
    QuestionBankSeries,
)
from apps.learning.policies import (
    effective_learning_quota,
    locked_account_quota_state,
    locked_daily_usage,
)

from .dispatch import GenerationDispatcher, dispatch_question_bank_generation

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class QuestionBankGenerationRequest:
    series_id: UUID
    state: str
    row_version: int


def _text(value: object, *, maximum: int, required: bool) -> str:
    if not isinstance(value, str):
        raise LearningCommandError(
            "learning.bank_configuration_invalid.v1", "题库配置不合法。"
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
            "learning.bank_configuration_invalid.v1", "题库配置不合法。"
        )
    return normalized


def _enabled_types(value: GenerationQuestionTypes) -> tuple[str, ...]:
    if not isinstance(value, GenerationQuestionTypes) or any(
        type(getattr(value, field)) is not bool for field in value.__dataclass_fields__
    ):
        raise LearningCommandError(
            "learning.bank_configuration_invalid.v1", "题库题型配置不合法。"
        )
    enabled = value.enabled()
    if not enabled:
        raise LearningCommandError(
            "learning.bank_configuration_invalid.v1", "至少选择一种题型。"
        )
    return enabled


def _existing(
    *,
    owner_id: UUID,
    idempotency_key: str,
    document_id: UUID,
    title: str,
    description: str,
    allowed_types: tuple[str, ...],
) -> QuestionBankGenerationRequest | None:
    series = QuestionBankSeries.objects.filter(
        owner_id=owner_id,
        submission_idempotency_key=idempotency_key,
    ).first()
    if series is None:
        return None
    if (
        series.source_document_id != document_id
        or series.base_title != title
        or series.description != description
        or tuple(series.allowed_question_types) != allowed_types
    ):
        raise LearningCommandError(
            "learning.idempotency_conflict.v1",
            "相同幂等标识已用于其他题库请求。",
        )
    return QuestionBankGenerationRequest(series.id, series.state, series.row_version)


def create_question_bank_generation_request(
    *,
    owner_id,
    document_id,
    base_title: str,
    description: str,
    question_types: GenerationQuestionTypes,
    idempotency_key: str,
    dispatcher: GenerationDispatcher,
    now: datetime | None = None,
) -> QuestionBankGenerationRequest:
    if (
        not isinstance(owner_id, UUID)
        or not isinstance(document_id, UUID)
        or not can_upload_attachments(owner_id)
        or not isinstance(idempotency_key, str)
        or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None
        or not callable(dispatcher)
    ):
        raise LearningCommandError(
            "learning.bank_configuration_invalid.v1", "题库配置不合法。"
        )
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "题库请求时间不合法。")
    title = _text(base_title, maximum=160, required=True)
    safe_description = _text(description, maximum=1_000, required=False)
    allowed_types = _enabled_types(question_types)
    existing = _existing(
        owner_id=owner_id,
        idempotency_key=idempotency_key,
        document_id=document_id,
        title=title,
        description=safe_description,
        allowed_types=allowed_types,
    )
    if existing is not None:
        transaction.on_commit(
            lambda: dispatch_question_bank_generation(
                existing.series_id,
                dispatcher=dispatcher,
                now=current,
            )
        )
        return existing
    try:
        with transaction.atomic():
            locked_account_quota_state(owner_id)
            existing = _existing(
                owner_id=owner_id,
                idempotency_key=idempotency_key,
                document_id=document_id,
                title=title,
                description=safe_description,
                allowed_types=allowed_types,
            )
            if existing is not None:
                transaction.on_commit(
                    lambda: dispatch_question_bank_generation(
                        existing.series_id,
                        dispatcher=dispatcher,
                        now=current,
                    )
                )
                return existing
            try:
                policy = LearningQuotaPolicy.objects.select_for_update().get(pk=1)
            except LearningQuotaPolicy.DoesNotExist:
                raise LearningCommandError(
                    "learning.quota_unavailable.v1", "业务配额暂不可用。"
                ) from None
            max_questions_per_volume = policy.max_questions_per_volume
            if max_questions_per_volume is None:
                raise LearningCommandError(
                    "learning.generation_not_configured.v1",
                    "管理员尚未配置单卷题数上限。",
                )
            try:
                document = KnowledgeDocument.objects.select_for_update().get(
                    pk=document_id,
                    owner_id=owner_id,
                    state=KnowledgeDocumentState.APPROVED,
                )
            except KnowledgeDocument.DoesNotExist:
                raise LearningCommandError(
                    "learning.document_not_available.v1",
                    "知识文档当前不能生成题库。",
                ) from None
            limits = effective_learning_quota(owner_id)
            usage = locked_daily_usage(owner_id, timezone.localdate(current))
            if usage.generations_accepted >= limits.daily_generations:
                raise LearningCommandError(
                    "learning.daily_generation_quota_exhausted.v1",
                    "今日题库生成额度已用完。",
                )
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
            if reserved + 1 > limits.unpurged_banks:
                raise LearningCommandError(
                    "learning.bank_quota_exhausted.v1",
                    "未清理题库数量已达上限。",
                )
            series = QuestionBankSeries(
                owner_id=owner_id,
                source_document=document,
                base_title=title,
                description=safe_description,
                allowed_question_types=list(allowed_types),
                max_questions_per_volume_snapshot=max_questions_per_volume,
                input_content_sha256=document.content_sha256,
                submission_idempotency_key=idempotency_key,
            )
            try:
                snapshot = create_agent_invocation(
                    profile_key=QUESTION_GENERATION_PROFILE_KEY,
                    caller_type="question_generation",
                    caller_id=f"{series.id}:1",
                    idempotency_key=f"generation:{series.id}:1",
                    estimated_input_tokens=document.estimated_tokens,
                )
            except AgentCommandError as error:
                raise LearningCommandError(error.code, str(error)) from None
            series.generation_snapshot_invocation_id = snapshot.id
            series.save(force_insert=True)
            usage.generations_accepted += 1
            usage.row_version += 1
            usage.save(
                update_fields=("generations_accepted", "row_version", "updated_at")
            )
            transaction.on_commit(
                lambda: dispatch_question_bank_generation(
                    series.id,
                    dispatcher=dispatcher,
                    now=current,
                )
            )
    except IntegrityError as error:
        existing = _existing(
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            document_id=document_id,
            title=title,
            description=safe_description,
            allowed_types=allowed_types,
        )
        if existing is not None:
            transaction.on_commit(
                lambda: dispatch_question_bank_generation(
                    existing.series_id,
                    dispatcher=dispatcher,
                    now=current,
                )
            )
            return existing
        raise LearningCommandError(
            "learning.bank_request_conflict.v1", "题库生成请求发生冲突。"
        ) from error
    return QuestionBankGenerationRequest(series.id, series.state, series.row_version)


__all__ = [
    "QuestionBankGenerationRequest",
    "create_question_bank_generation_request",
]
