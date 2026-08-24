from dataclasses import dataclass

from apps.learning.contracts import LearningCommandError
from apps.learning.models import KnowledgeDocument
from apps.media.public import MediaStorage, stream_authorized_text

from .review_inputs import review_input_blocks
from .token_estimate import estimate_text_tokens


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentInput:
    content: str
    blocks: tuple[str, ...]
    estimated_tokens: int


def knowledge_document_input(
    document: KnowledgeDocument,
    *,
    storage: MediaStorage | None,
) -> KnowledgeDocumentInput:
    if not isinstance(document, KnowledgeDocument) or document.media_asset_id is None:
        raise LearningCommandError(
            "learning.document_not_available.v1",
            "知识文档内容当前不可用。",
        )
    with stream_authorized_text(
        actor_id=document.owner_id,
        asset_id=document.media_asset_id,
        storage=storage,
    ) as opened:
        content = "".join(opened.chunks)
    content = content.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = review_input_blocks(content)
    return KnowledgeDocumentInput(
        content=content,
        blocks=blocks,
        estimated_tokens=document.estimated_tokens or estimate_text_tokens(content),
    )


__all__ = ["KnowledgeDocumentInput", "knowledge_document_input"]
