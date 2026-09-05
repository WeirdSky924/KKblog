from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator

from apps.core.pagination import page_window
from apps.learning.contracts import LearningCommandError
from apps.learning.models import KnowledgeDocument, KnowledgeDocumentAccess


@dataclass(frozen=True, slots=True)
class OwnerDocumentAccessItem:
    purpose: str
    accessed_at: datetime


@dataclass(frozen=True, slots=True)
class OwnerDocumentAccessPage:
    items: tuple[OwnerDocumentAccessItem, ...]
    page_number: int
    total_pages: int
    total_items: int
    has_previous: bool
    has_next: bool

    @property
    def page_window(self) -> tuple[int | None, ...]:
        return page_window(self.page_number, self.total_pages)


def owner_document_access_history(
    *,
    owner_id: UUID,
    document_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> OwnerDocumentAccessPage:
    if (
        not isinstance(owner_id, UUID)
        or not isinstance(document_id, UUID)
        or isinstance(page, bool)
        or not isinstance(page, int)
        or page < 1
        or isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= 100
        or not KnowledgeDocument.objects.filter(
            pk=document_id,
            owner_id=owner_id,
        ).exists()
    ):
        raise LearningCommandError("learning.document_not_found.v1", "知识文档不存在。")
    paginator = Paginator(
        KnowledgeDocumentAccess.objects.filter(document_id=document_id).order_by(
            "-accessed_at", "-id"
        ),
        page_size,
    )
    selected = paginator.get_page(page)
    return OwnerDocumentAccessPage(
        items=tuple(
            OwnerDocumentAccessItem(item.purpose, item.accessed_at)
            for item in selected.object_list
        ),
        page_number=selected.number,
        total_pages=paginator.num_pages,
        total_items=paginator.count,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


__all__ = [
    "OwnerDocumentAccessItem",
    "OwnerDocumentAccessPage",
    "owner_document_access_history",
]
