from django.db import models

from apps.core.ids import new_ulid


class ImportJob(models.Model):
    class SourceKind(models.TextChoices):
        MARKDOWN = "MARKDOWN", "Markdown"
        ZIP = "ZIP", "ZIP"

    class Status(models.TextChoices):
        PARSING = "PARSING", "解析中"
        PREVIEW_READY = "PREVIEW_READY", "预览就绪"
        PROCESSING = "PROCESSING", "导入中"
        COMPLETED = "COMPLETED", "完成"
        PARTIAL = "PARTIAL", "部分完成"
        FAILED = "FAILED", "失败"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    author = models.ForeignKey(
        "accounts.Account",
        related_name="import_jobs",
        on_delete=models.CASCADE,
        editable=False,
    )
    source_kind = models.CharField(
        max_length=12,
        choices=SourceKind.choices,
        editable=False,
    )
    source_name = models.CharField(max_length=255, editable=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PARSING,
        editable=False,
    )
    preview_version = models.PositiveBigIntegerField(default=1, editable=False)
    confirmed_preview_version = models.PositiveBigIntegerField(
        null=True,
        editable=False,
    )
    preview_summary = models.JSONField(default=dict, editable=False)
    result_summary = models.JSONField(default=dict, editable=False)
    error_code = models.CharField(max_length=96, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    previewed_at = models.DateTimeField(null=True, editable=False)
    confirmed_at = models.DateTimeField(null=True, editable=False)
    completed_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        db_table = "exchange_import_job"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("author", "-created_at"),
                name="exchange_import_author_idx",
            ),
            models.Index(
                fields=("status", "created_at"),
                name="exchange_import_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(preview_version__gte=1),
                name="exchange_import_preview_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(confirmed_preview_version__isnull=True)
                    | models.Q(confirmed_preview_version__gte=1)
                ),
                name="exchange_import_confirmed_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="PARSING",
                        previewed_at__isnull=True,
                        confirmed_preview_version__isnull=True,
                        confirmed_at__isnull=True,
                        completed_at__isnull=True,
                        error_code="",
                    )
                    | models.Q(
                        status="PREVIEW_READY",
                        previewed_at__isnull=False,
                        confirmed_preview_version__isnull=True,
                        confirmed_at__isnull=True,
                        completed_at__isnull=True,
                        error_code="",
                    )
                    | models.Q(
                        status="PROCESSING",
                        previewed_at__isnull=False,
                        confirmed_preview_version__isnull=False,
                        confirmed_at__isnull=False,
                        completed_at__isnull=True,
                        error_code="",
                    )
                    | models.Q(
                        status__in=("COMPLETED", "PARTIAL"),
                        previewed_at__isnull=False,
                        confirmed_preview_version__isnull=False,
                        confirmed_at__isnull=False,
                        completed_at__isnull=False,
                        error_code="",
                    )
                    | models.Q(
                        status="FAILED",
                        confirmed_preview_version__isnull=True,
                        confirmed_at__isnull=True,
                        completed_at__isnull=True,
                    )
                    & ~models.Q(error_code="")
                    | models.Q(
                        status="FAILED",
                        previewed_at__isnull=False,
                        confirmed_preview_version__isnull=False,
                        confirmed_at__isnull=False,
                        completed_at__isnull=False,
                    )
                    & ~models.Q(error_code="")
                ),
                name="exchange_import_job_state_shape",
            ),
        ]
