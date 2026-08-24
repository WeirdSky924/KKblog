from django.db import models
from django.db.models import Q

from apps.core.ids import new_uuid
from apps.learning.contracts import KnowledgeDocumentState, LearningDeletionActor

_CONTENT_STATES = (
    KnowledgeDocumentState.STAGED,
    KnowledgeDocumentState.REVIEW_PENDING,
    KnowledgeDocumentState.REVIEWING,
    KnowledgeDocumentState.APPROVED,
    KnowledgeDocumentState.REJECTED,
    KnowledgeDocumentState.REVIEW_FAILED,
    KnowledgeDocumentState.DELETE_PENDING,
)
_PURGED_STATES = (
    KnowledgeDocumentState.CONTENT_PURGED,
    KnowledgeDocumentState.DELETED,
)
_FAILURE_STATES = (
    KnowledgeDocumentState.REJECTED,
    KnowledgeDocumentState.REVIEW_FAILED,
)
_RESTORABLE_STATES = tuple(
    state for state in _CONTENT_STATES if state != KnowledgeDocumentState.DELETE_PENDING
)


class KnowledgeDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    owner = models.ForeignKey(
        "accounts.Account",
        related_name="knowledge_documents",
        on_delete=models.PROTECT,
    )
    media_asset_id = models.CharField(max_length=26, null=True, blank=True)
    original_name = models.CharField(max_length=255, null=True, blank=True)
    title = models.CharField(max_length=200, null=True, blank=True)
    summary = models.CharField(max_length=500, null=True, blank=True)
    content_sha256 = models.CharField(max_length=64, null=True, blank=True)
    character_count = models.PositiveIntegerField(null=True, blank=True)
    line_count = models.PositiveIntegerField(null=True, blank=True)
    estimated_tokens = models.PositiveIntegerField(null=True, blank=True)
    state = models.CharField(
        max_length=24,
        choices=KnowledgeDocumentState.choices,
        default=KnowledgeDocumentState.STAGED,
    )
    statement_version = models.CharField(max_length=64, null=True, blank=True)
    statement_accepted_by = models.ForeignKey(
        "accounts.Account",
        related_name="accepted_knowledge_statements",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    statement_accepted_at = models.DateTimeField(null=True, blank=True)
    submission_idempotency_key = models.CharField(max_length=128)
    last_reason_code = models.CharField(max_length=96, blank=True, default="")
    safe_status_summary = models.CharField(max_length=500, null=True, blank=True)
    admin_lock_reason = models.CharField(max_length=96, blank=True, default="")
    admin_hidden_at = models.DateTimeField(null=True, blank=True, editable=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    pre_delete_state = models.CharField(
        max_length=24,
        choices=KnowledgeDocumentState.choices,
        null=True,
        blank=True,
        editable=False,
    )
    deletion_requested_at = models.DateTimeField(null=True, blank=True, editable=False)
    deletion_actor = models.CharField(
        max_length=8,
        choices=LearningDeletionActor.choices,
        blank=True,
        default="",
        editable=False,
    )
    purge_after = models.DateTimeField(null=True, blank=True, editable=False)
    failure_purge_after = models.DateTimeField(null=True, blank=True, editable=False)
    content_purged_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "learning_knowledge_document"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(state__in=KnowledgeDocumentState.values),
                name="learning_document_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="learning_document_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state__in=_CONTENT_STATES,
                        media_asset_id__isnull=False,
                        original_name__isnull=False,
                        title__isnull=False,
                        summary__isnull=False,
                        content_sha256__isnull=False,
                        character_count__gte=1,
                        line_count__gte=1,
                        estimated_tokens__gte=1,
                        statement_version__isnull=False,
                        statement_accepted_by__isnull=False,
                        statement_accepted_at__isnull=False,
                    )
                    | Q(
                        state__in=_PURGED_STATES,
                        media_asset_id__isnull=True,
                        original_name__isnull=True,
                        title__isnull=True,
                        summary__isnull=True,
                        content_sha256__isnull=True,
                        character_count__isnull=True,
                        line_count__isnull=True,
                        estimated_tokens__isnull=True,
                        statement_version__isnull=True,
                        statement_accepted_by__isnull=True,
                        statement_accepted_at__isnull=True,
                    )
                ),
                name="learning_document_content_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=KnowledgeDocumentState.DELETE_PENDING,
                        pre_delete_state__in=_RESTORABLE_STATES,
                        deletion_requested_at__isnull=False,
                        purge_after__isnull=False,
                    )
                    | (
                        ~Q(state=KnowledgeDocumentState.DELETE_PENDING)
                        & Q(
                            pre_delete_state__isnull=True,
                            deletion_requested_at__isnull=True,
                            purge_after__isnull=True,
                        )
                    )
                ),
                name="learning_document_deletion_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state=KnowledgeDocumentState.DELETE_PENDING,
                        deletion_actor__in=LearningDeletionActor.values,
                    )
                    | (
                        ~Q(state=KnowledgeDocumentState.DELETE_PENDING)
                        & Q(deletion_actor="")
                    )
                ),
                name="learning_document_deletion_actor_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(admin_hidden_at__isnull=True, admin_lock_reason="")
                    | (Q(admin_hidden_at__isnull=False) & ~Q(admin_lock_reason=""))
                    | (
                        Q(
                            state=KnowledgeDocumentState.DELETE_PENDING,
                            deletion_actor=LearningDeletionActor.ADMINISTRATOR,
                        )
                        & ~Q(admin_lock_reason="")
                    )
                ),
                name="learning_document_admin_lock_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state__in=_FAILURE_STATES, failure_purge_after__isnull=False)
                    | Q(
                        state=KnowledgeDocumentState.DELETE_PENDING,
                        pre_delete_state__in=_FAILURE_STATES,
                        failure_purge_after__isnull=False,
                    )
                    | (
                        ~Q(
                            state__in=(
                                *_FAILURE_STATES,
                                KnowledgeDocumentState.DELETE_PENDING,
                            )
                        )
                        & Q(failure_purge_after__isnull=True)
                    )
                    | Q(
                        state=KnowledgeDocumentState.DELETE_PENDING,
                        pre_delete_state__in=tuple(
                            state
                            for state in _RESTORABLE_STATES
                            if state not in _FAILURE_STATES
                        ),
                        failure_purge_after__isnull=True,
                    )
                ),
                name="learning_document_failure_purge_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state__in=_PURGED_STATES, content_purged_at__isnull=False)
                    | (~Q(state__in=_PURGED_STATES) & Q(content_purged_at__isnull=True))
                ),
                name="learning_document_purged_at_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state=KnowledgeDocumentState.DELETED, deleted_at__isnull=False)
                    | (
                        ~Q(state=KnowledgeDocumentState.DELETED)
                        & Q(deleted_at__isnull=True)
                    )
                ),
                name="learning_document_deleted_at_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(content_sha256__isnull=True)
                    | Q(content_sha256__regex=r"^[0-9a-f]{64}$")
                ),
                name="learning_document_sha_shape",
            ),
            models.UniqueConstraint(
                fields=("owner", "content_sha256"),
                condition=Q(content_sha256__isnull=False),
                name="learning_document_owner_sha_unique",
            ),
            models.UniqueConstraint(
                fields=("owner", "submission_idempotency_key"),
                name="learning_document_owner_idempotency_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("owner", "state", "-created_at", "id"),
                name="learn_doc_owner_state_idx",
            ),
            models.Index(
                fields=("state", "purge_after", "id"),
                name="learning_document_purge_idx",
            ),
            models.Index(
                fields=("state", "failure_purge_after", "id"),
                name="learning_document_failure_idx",
            ),
            models.Index(
                fields=("admin_hidden_at", "state", "-created_at", "id"),
                name="learning_document_admin_idx",
            ),
        ]
