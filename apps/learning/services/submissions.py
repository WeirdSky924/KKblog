import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import PurePath
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.public import can_upload_attachments
from apps.learning.contracts import (
    CURRENT_UPLOAD_STATEMENT_VERSION,
    DocumentSubmissionOutcome,
    KnowledgeDocumentState,
    KnowledgeReviewRunState,
    LearningCommandError,
)
from apps.learning.models import (
    KnowledgeDocument,
    KnowledgeReviewRun,
)
from apps.learning.policies import (
    effective_learning_quota,
    locked_account_quota_state,
    locked_daily_usage,
)
from apps.media.public import (
    BindingInput,
    MediaAccessError,
    MediaBindingError,
    MediaStorage,
    MediaTargetType,
    bind_assets,
    stream_owned_text_upload,
)

from .dispatch import ReviewDispatcher, dispatch_knowledge_review_run
from .token_estimate import estimate_text_tokens

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_PENDING_STATES = (
    KnowledgeDocumentState.REVIEW_PENDING,
    KnowledgeDocumentState.REVIEWING,
)


@dataclass(frozen=True, slots=True)
class DocumentSubmissionResult:
    document_id: UUID
    review_run_id: UUID
    state: str
    outcome: DocumentSubmissionOutcome


@dataclass(frozen=True, slots=True)
class _DocumentMetadata:
    asset_id: str
    original_name: str
    title: str
    summary: str
    content_sha256: str
    character_count: int
    line_count: int
    estimated_tokens: int


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError("learning.time_invalid.v1", "知识文档时间不合法。")
    return current


def _validated_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_KEY.fullmatch(value) is None:
        raise LearningCommandError(
            "learning.idempotency_invalid.v1", "提交幂等标识不合法。"
        )
    return value


def _validate_statement(*, statement_version: str, accepted: bool) -> None:
    if accepted is not True:
        raise LearningCommandError(
            "learning.statement_required.v1", "必须明确同意当前上传声明。"
        )
    if statement_version != CURRENT_UPLOAD_STATEMENT_VERSION:
        raise LearningCommandError(
            "learning.statement_outdated.v1", "上传声明已更新，请重新确认。"
        )


def _normalized_content(content: str) -> str:
    normalized = (
        content.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    )
    if not normalized or not normalized.strip():
        raise LearningCommandError("learning.document_empty.v1", "知识文档不能为空。")
    if any(
        unicodedata.category(character) == "Cc" and character not in {"\n", "\t"}
        for character in normalized
    ):
        raise LearningCommandError(
            "learning.document_control_character.v1",
            "知识文档包含不支持的控制字符。",
        )
    return normalized


def _title_and_summary(content: str, original_name: str) -> tuple[str, str]:
    title = ""
    summary = ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _HEADING.fullmatch(line)
        if heading is not None and not title:
            title = heading.group(1).strip()
            continue
        if heading is None and not line.startswith("```") and not summary:
            summary = line
        if title and summary:
            break
    if not title:
        title = PurePath(original_name).stem.strip() or "知识文档"
    if not summary:
        summary = title
    return title[:200], summary[:500]


def _read_metadata(
    *,
    owner_id: UUID,
    asset_id: str,
    storage: MediaStorage | None,
) -> _DocumentMetadata:
    try:
        with stream_owned_text_upload(
            owner_id=owner_id,
            asset_id=asset_id,
            storage=storage,
        ) as opened:
            content = _normalized_content("".join(opened.chunks))
            original_name = opened.original_name
    except MediaAccessError:
        raise LearningCommandError(
            "learning.asset_unavailable.v1", "知识文档文件不存在或不可用。"
        ) from None
    title, summary = _title_and_summary(content, original_name)
    encoded = content.encode("utf-8")
    return _DocumentMetadata(
        asset_id=asset_id,
        original_name=original_name,
        title=title,
        summary=summary,
        content_sha256=sha256(encoded).hexdigest(),
        character_count=len(content),
        line_count=content.count("\n") + 1,
        estimated_tokens=estimate_text_tokens(content),
    )


def _existing_result(
    *, owner_id: UUID, idempotency_key: str, asset_id: str
) -> DocumentSubmissionResult | None:
    existing = KnowledgeDocument.objects.filter(
        owner_id=owner_id,
        submission_idempotency_key=idempotency_key,
    ).first()
    if existing is None:
        return None
    if existing.media_asset_id != asset_id:
        raise LearningCommandError(
            "learning.idempotency_conflict.v1",
            "相同幂等标识已用于其他知识文档。",
        )
    run = existing.review_runs.order_by("-sequence").first()
    if run is None:
        raise LearningCommandError(
            "learning.document_conflict.v1", "知识文档提交状态不完整。"
        )
    return DocumentSubmissionResult(
        document_id=existing.id,
        review_run_id=run.id,
        state=existing.state,
        outcome=DocumentSubmissionOutcome.IDEMPOTENT,
    )


def submit_knowledge_document(
    *,
    owner_id,
    asset_id: str,
    statement_version: str,
    accepted: bool,
    idempotency_key: str,
    dispatcher: ReviewDispatcher,
    storage: MediaStorage | None = None,
    now: datetime | None = None,
) -> DocumentSubmissionResult:
    if (
        not isinstance(owner_id, UUID)
        or not can_upload_attachments(owner_id)
        or not callable(dispatcher)
    ):
        raise LearningCommandError(
            "learning.attachment_capability_required.v1",
            "当前账户没有知识文档上传能力。",
        )
    current = _current_time(now)
    stable_key = _validated_idempotency_key(idempotency_key)
    _validate_statement(statement_version=statement_version, accepted=accepted)
    existing = _existing_result(
        owner_id=owner_id,
        idempotency_key=stable_key,
        asset_id=asset_id,
    )
    if existing is not None:
        transaction.on_commit(
            lambda: dispatch_knowledge_review_run(
                existing.review_run_id,
                dispatcher=dispatcher,
            )
        )
        return existing
    metadata = _read_metadata(
        owner_id=owner_id,
        asset_id=asset_id,
        storage=storage,
    )

    try:
        with transaction.atomic():
            locked_account_quota_state(owner_id)
            existing = _existing_result(
                owner_id=owner_id,
                idempotency_key=stable_key,
                asset_id=asset_id,
            )
            if existing is not None:
                transaction.on_commit(
                    lambda: dispatch_knowledge_review_run(
                        existing.review_run_id,
                        dispatcher=dispatcher,
                    )
                )
                return existing
            duplicate = KnowledgeDocument.objects.filter(
                owner_id=owner_id,
                content_sha256=metadata.content_sha256,
            ).first()
            if duplicate is not None:
                raise LearningCommandError(
                    "learning.document_duplicate.v1",
                    "相同内容的知识文档已经存在。",
                    document_id=duplicate.id,
                )
            limits = effective_learning_quota(owner_id)
            usage = locked_daily_usage(owner_id, timezone.localdate(current))
            if usage.uploads_created >= limits.daily_uploads:
                raise LearningCommandError(
                    "learning.daily_upload_quota_exhausted.v1",
                    "今日知识文档上传额度已用完。",
                )
            pending_count = KnowledgeDocument.objects.filter(
                owner_id=owner_id,
                state__in=_PENDING_STATES,
            ).count()
            if pending_count >= limits.pending_reviews:
                raise LearningCommandError(
                    "learning.pending_quota_exhausted.v1",
                    "待审核知识文档数量已达上限。",
                )
            document = KnowledgeDocument.objects.create(
                owner_id=owner_id,
                media_asset_id=metadata.asset_id,
                original_name=metadata.original_name,
                title=metadata.title,
                summary=metadata.summary,
                content_sha256=metadata.content_sha256,
                character_count=metadata.character_count,
                line_count=metadata.line_count,
                estimated_tokens=metadata.estimated_tokens,
                state=KnowledgeDocumentState.STAGED,
                statement_version=statement_version,
                statement_accepted_by_id=owner_id,
                statement_accepted_at=current,
                submission_idempotency_key=stable_key,
            )
            try:
                bind_assets(
                    actor_id=owner_id,
                    target_type=MediaTargetType.LEARNING_DOCUMENT,
                    target_id=str(document.id),
                    inputs=(BindingInput(metadata.asset_id, "source"),),
                )
            except MediaBindingError:
                raise LearningCommandError(
                    "learning.asset_unavailable.v1",
                    "知识文档文件不存在或不可用。",
                ) from None
            run = KnowledgeReviewRun.objects.create(
                document=document,
                sequence=1,
                state=KnowledgeReviewRunState.PENDING,
                input_content_sha256=metadata.content_sha256,
                idempotency_key=f"review:{document.id}:1",
            )
            document.state = KnowledgeDocumentState.REVIEW_PENDING
            document.save(update_fields=("state", "updated_at"))
            usage.uploads_created += 1
            usage.row_version += 1
            usage.save(update_fields=("uploads_created", "row_version", "updated_at"))
            transaction.on_commit(
                lambda: dispatch_knowledge_review_run(
                    run.id,
                    dispatcher=dispatcher,
                )
            )
    except IntegrityError as exc:
        duplicate = KnowledgeDocument.objects.filter(
            owner_id=owner_id,
            content_sha256=metadata.content_sha256,
        ).first()
        if duplicate is not None:
            raise LearningCommandError(
                "learning.document_duplicate.v1",
                "相同内容的知识文档已经存在。",
                document_id=duplicate.id,
            ) from exc
        raise LearningCommandError(
            "learning.document_conflict.v1", "知识文档提交发生冲突。"
        ) from exc
    return DocumentSubmissionResult(
        document_id=document.id,
        review_run_id=run.id,
        state=document.state,
        outcome=DocumentSubmissionOutcome.CREATED,
    )
