from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.learning.contracts import KnowledgeDocumentAccessPurpose


class KnowledgeDocumentAccess(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    document = models.ForeignKey(
        "learning.KnowledgeDocument",
        related_name="access_events",
        on_delete=models.PROTECT,
    )
    administrator_actor = models.ForeignKey(
        "accounts.Account",
        related_name="knowledge_document_access_events",
        on_delete=models.PROTECT,
    )
    purpose = models.CharField(
        max_length=24,
        choices=KnowledgeDocumentAccessPurpose.choices,
    )
    trace_code = models.CharField(max_length=30)
    accessed_at = models.DateTimeField()

    class Meta:
        db_table = "learning_knowledge_document_access"
        ordering = ("-accessed_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("document", "administrator_actor", "purpose", "trace_code"),
                name="learning_document_access_trace_unique",
            ),
            models.CheckConstraint(
                condition=Q(purpose__in=KnowledgeDocumentAccessPurpose.values),
                name="learning_document_access_purpose_valid",
            ),
            models.CheckConstraint(
                condition=Q(trace_code__regex=r"^trc_[0-9a-hjkmnp-tv-z]{26}$"),
                name="learning_document_access_trace_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("document", "-accessed_at", "id"),
                name="learn_doc_access_hist_idx",
            )
        ]
