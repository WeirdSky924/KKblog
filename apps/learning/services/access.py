import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.public import is_active_account, is_administrator
from apps.learning.contracts import (
    KnowledgeDocumentAccessPurpose,
    KnowledgeDocumentState,
    LearningCommandError,
)
from apps.learning.models import KnowledgeDocument, KnowledgeDocumentAccess
from apps.media.public import (
    MediaAccessError,
    MediaStorage,
    MediaTextReadError,
    stream_authorized_text,
)

_TRACE_CODE = re.compile(r"^trc_[0-9a-hjkmnp-tv-z]{26}$")
_READABLE_STATES = (
    KnowledgeDocumentState.REVIEW_PENDING,
    KnowledgeDocumentState.REVIEWING,
    KnowledgeDocumentState.APPROVED,
    KnowledgeDocumentState.REJECTED,
    KnowledgeDocumentState.REVIEW_FAILED,
)


@dataclass(frozen=True, slots=True)
class AuthorizedKnowledgeDocumentText:
    document_id: UUID
    original_name: str
    content: str
    size_bytes: int
    content_sha256: str


def _current_time(now: datetime | None) -> datetime:
    current = now or timezone.now()
    if not isinstance(current, datetime) or not timezone.is_aware(current):
        raise LearningCommandError(
            "learning.time_invalid.v1", "知识文档访问时间不合法。"
        )
    return current


def read_knowledge_document_text(
    *,
    actor_id,
    document_id,
    purpose,
    trace_code: str,
    storage: MediaStorage | None = None,
    now: datetime | None = None,
) -> AuthorizedKnowledgeDocumentText:
    if (
        not isinstance(actor_id, UUID)
        or not isinstance(document_id, UUID)
        or not isinstance(trace_code, str)
        or _TRACE_CODE.fullmatch(trace_code) is None
    ):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    try:
        normalized_purpose = KnowledgeDocumentAccessPurpose(purpose)
        document = KnowledgeDocument.objects.get(pk=document_id)
    except (KnowledgeDocument.DoesNotExist, TypeError, ValueError):
        raise LearningCommandError(
            "learning.document_not_found.v1", "知识文档不存在。"
        ) from None
    owner = actor_id == document.owner_id and is_active_account(actor_id)
    administrator = is_administrator(actor_id)
    if (
        document.state not in _READABLE_STATES
        or document.media_asset_id is None
        or (
            owner
            and not administrator
            and normalized_purpose != KnowledgeDocumentAccessPurpose.OWNER_VIEW
        )
        or (
            administrator
            and not owner
            and normalized_purpose == KnowledgeDocumentAccessPurpose.OWNER_VIEW
        )
        or not (owner or administrator)
    ):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    try:
        with stream_authorized_text(
            actor_id=actor_id,
            asset_id=document.media_asset_id,
            storage=storage,
        ) as opened:
            content = "".join(opened.chunks)
            result = AuthorizedKnowledgeDocumentText(
                document.id,
                opened.original_name,
                content,
                opened.size_bytes,
                document.content_sha256,
            )
    except (MediaAccessError, MediaTextReadError):
        raise LearningCommandError(
            "learning.document_not_found.v1", "知识文档不存在。"
        ) from None
    if (
        administrator
        and normalized_purpose == KnowledgeDocumentAccessPurpose.ADMIN_REVIEW
    ):
        current = _current_time(now)
        with transaction.atomic():
            KnowledgeDocumentAccess.objects.get_or_create(
                document=document,
                administrator_actor_id=actor_id,
                purpose=normalized_purpose,
                trace_code=trace_code,
                defaults={"accessed_at": current},
            )
    return result


__all__ = ["AuthorizedKnowledgeDocumentText", "read_knowledge_document_text"]
