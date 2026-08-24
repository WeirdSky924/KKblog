from uuid import UUID

from apps.accounts.public import (
    can_upload_attachments,
    is_active_account,
    is_administrator,
)
from apps.learning.contracts import KnowledgeDocumentState
from apps.media.public import (
    MediaPurpose,
    MediaTargetType,
    MediaUploadAdapter,
    TargetAccessDecision,
    TargetAccessRequest,
    register_media_upload_adapter,
    register_target_access,
)

from .models import KnowledgeDocument


def knowledge_document_media_access(
    request: TargetAccessRequest,
) -> TargetAccessDecision:
    try:
        document_id = UUID(request.target_id)
        document = KnowledgeDocument.objects.only("owner_id", "state").get(
            pk=document_id
        )
    except (KnowledgeDocument.DoesNotExist, TypeError, ValueError):
        return TargetAccessDecision(False, False, False, False)
    owner = request.actor_id == document.owner_id
    readable = document.state not in {
        KnowledgeDocumentState.DELETE_PENDING,
        KnowledgeDocumentState.CONTENT_PURGED,
        KnowledgeDocumentState.DELETED,
    }
    return TargetAccessDecision(
        exists=True,
        can_bind=(
            owner
            and document.state == KnowledgeDocumentState.STAGED
            and can_upload_attachments(request.actor_id)
        ),
        can_read=(
            readable
            and (
                (owner and is_active_account(request.actor_id))
                or is_administrator(request.actor_id)
            )
        ),
        public_immutable=False,
        binding_scope=str(document.id),
    )


def register_media_access() -> None:
    register_target_access(
        MediaTargetType.LEARNING_DOCUMENT,
        knowledge_document_media_access,
        replace=True,
    )
    register_media_upload_adapter(
        MediaUploadAdapter(
            key="knowledge-document",
            purpose=MediaPurpose.KNOWLEDGE_DOCUMENT,
            input_name="source_asset_id",
            access=can_upload_attachments,
        ),
        replace=True,
    )
