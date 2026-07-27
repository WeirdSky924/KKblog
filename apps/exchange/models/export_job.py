from django.db import models

from apps.core.ids import new_ulid


class ExportJob(models.Model):
    class Scope(models.TextChoices):
        ALL = "ALL", "全站"
        AUTHOR = "AUTHOR", "作者"
        SECTION = "SECTION", "分区"
        ARTICLES = "ARTICLES", "选中文章"

    class State(models.TextChoices):
        RUNNING = "RUNNING", "进行中"
        CANCEL_REQUESTED = "CANCEL_REQUESTED", "取消中"
        COMPLETED = "COMPLETED", "已完成"
        CANCELLED = "CANCELLED", "已取消"
        FAILED = "FAILED", "失败"
        EXPIRED = "EXPIRED", "已过期"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    requested_by = models.ForeignKey(
        "accounts.Account",
        related_name="export_jobs",
        on_delete=models.PROTECT,
        editable=False,
    )
    scope = models.CharField(max_length=12, choices=Scope.choices, editable=False)
    scope_author_id = models.UUIDField(null=True, editable=False)
    scope_section_id = models.UUIDField(null=True, editable=False)
    requested_article_ids = models.JSONField(default=list, editable=False)
    selection_summary = models.JSONField(default=dict, editable=False)
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.RUNNING,
        editable=False,
    )
    archive_key = models.CharField(max_length=512, blank=True, editable=False)
    archive_size_bytes = models.PositiveBigIntegerField(null=True, editable=False)
    archive_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    error_code = models.CharField(max_length=96, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    started_at = models.DateTimeField(editable=False)
    heartbeat_at = models.DateTimeField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    cancel_requested_at = models.DateTimeField(null=True, editable=False)
    completed_at = models.DateTimeField(null=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, editable=False)
    expires_at = models.DateTimeField(null=True, editable=False)
    expired_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        db_table = "exchange_export_job"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("state", "created_at"),
                name="exchange_export_state_idx",
            ),
            models.Index(
                fields=("requested_by", "-created_at"),
                name="exchange_export_requester_idx",
            ),
            models.Index(
                fields=("expires_at", "id"),
                condition=models.Q(state="COMPLETED"),
                name="exchange_export_expiry_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(state__in=("RUNNING", "CANCEL_REQUESTED")),
                name="exchange_export_active_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        scope="ALL",
                        scope_author_id__isnull=True,
                        scope_section_id__isnull=True,
                        requested_article_ids=[],
                    )
                    | models.Q(
                        scope="AUTHOR",
                        scope_author_id__isnull=False,
                        scope_section_id__isnull=True,
                        requested_article_ids=[],
                    )
                    | models.Q(
                        scope="SECTION",
                        scope_author_id__isnull=True,
                        scope_section_id__isnull=False,
                        requested_article_ids=[],
                    )
                    | models.Q(
                        scope="ARTICLES",
                        scope_author_id__isnull=True,
                        scope_section_id__isnull=True,
                    )
                    & ~models.Q(requested_article_ids=[])
                ),
                name="exchange_export_scope_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="RUNNING",
                        cancel_requested_at__isnull=True,
                        completed_at__isnull=True,
                        cancelled_at__isnull=True,
                        expires_at__isnull=True,
                        expired_at__isnull=True,
                        archive_key="",
                        archive_size_bytes__isnull=True,
                        archive_sha256="",
                        error_code="",
                    )
                    | models.Q(
                        state="CANCEL_REQUESTED",
                        cancel_requested_at__isnull=False,
                        completed_at__isnull=True,
                        cancelled_at__isnull=True,
                        expires_at__isnull=True,
                        expired_at__isnull=True,
                        archive_key="",
                        archive_size_bytes__isnull=True,
                        archive_sha256="",
                        error_code="",
                    )
                    | models.Q(
                        state="COMPLETED",
                        cancel_requested_at__isnull=True,
                        completed_at__isnull=False,
                        cancelled_at__isnull=True,
                        expires_at__isnull=False,
                        expired_at__isnull=True,
                        archive_size_bytes__isnull=False,
                        error_code="",
                    )
                    & ~models.Q(archive_key="")
                    & models.Q(archive_sha256__regex=r"^[0-9a-f]{64}$")
                    | models.Q(
                        state="CANCELLED",
                        cancel_requested_at__isnull=False,
                        completed_at__isnull=True,
                        cancelled_at__isnull=False,
                        expires_at__isnull=True,
                        expired_at__isnull=True,
                        archive_key="",
                        archive_size_bytes__isnull=True,
                        archive_sha256="",
                        error_code="",
                    )
                    | models.Q(
                        state="FAILED",
                        cancel_requested_at__isnull=True,
                        completed_at__isnull=False,
                        cancelled_at__isnull=True,
                        expires_at__isnull=True,
                        expired_at__isnull=True,
                        archive_key="",
                        archive_size_bytes__isnull=True,
                        archive_sha256="",
                    )
                    & ~models.Q(error_code="")
                    | models.Q(
                        state="EXPIRED",
                        cancel_requested_at__isnull=True,
                        completed_at__isnull=False,
                        cancelled_at__isnull=True,
                        expires_at__isnull=False,
                        expired_at__isnull=False,
                        archive_key="",
                        archive_size_bytes__isnull=False,
                        error_code="",
                    )
                    & models.Q(archive_sha256__regex=r"^[0-9a-f]{64}$")
                ),
                name="exchange_export_state_shape",
            ),
        ]


class ExportSelection(models.Model):
    job = models.ForeignKey(
        ExportJob,
        related_name="selections",
        on_delete=models.CASCADE,
        editable=False,
    )
    ordinal = models.PositiveIntegerField(editable=False)
    article_id = models.CharField(max_length=26, editable=False)
    author_id = models.UUIDField(editable=False)
    publication_state = models.CharField(max_length=16, editable=False)
    visibility = models.CharField(max_length=16, editable=False)
    section_id = models.UUIDField(null=True, editable=False)
    revision_ids = models.JSONField(default=list, editable=False)
    working_revision_id = models.CharField(max_length=26, null=True, editable=False)
    published_revision_id = models.CharField(max_length=26, null=True, editable=False)
    scheduled_revision_id = models.CharField(max_length=26, null=True, editable=False)
    scheduled_for = models.DateTimeField(null=True, editable=False)
    published_at = models.DateTimeField(null=True, editable=False)
    deleted_at = models.DateTimeField(null=True, editable=False)
    purge_after = models.DateTimeField(null=True, editable=False)

    class Meta:
        db_table = "exchange_export_selection"
        ordering = ("job_id", "ordinal")
        constraints = [
            models.UniqueConstraint(
                fields=("job", "ordinal"),
                name="exchange_export_selection_ordinal_unique",
            ),
            models.UniqueConstraint(
                fields=("job", "article_id"),
                name="exchange_export_selection_article_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(ordinal__gte=1),
                name="exchange_export_selection_ordinal_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(revision_ids=[]),
                name="exchange_export_selection_revisions_nonempty",
            ),
        ]
