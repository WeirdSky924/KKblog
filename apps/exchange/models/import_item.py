from django.db import models

from apps.core.ids import new_ulid


class ImportItem(models.Model):
    class ParseStatus(models.TextChoices):
        VALID = "VALID", "有效"
        INVALID = "INVALID", "无效"

    class Classification(models.TextChoices):
        NEW = "NEW", "新文章"
        DUPLICATE_ID = "DUPLICATE_ID", "重复 ID"
        TITLE_WARNING = "TITLE_WARNING", "同标题警告"
        FOREIGN_CONFLICT = "FOREIGN_CONFLICT", "跨作者冲突"
        INVALID = "INVALID", "无效"

    class Decision(models.TextChoices):
        SKIP = "SKIP", "跳过"
        UPDATE = "UPDATE", "更新"
        CREATE = "CREATE", "新建"

    class ResultStatus(models.TextChoices):
        PENDING = "PENDING", "待处理"
        SUCCESS = "SUCCESS", "成功"
        SKIPPED = "SKIPPED", "跳过"
        FAILED = "FAILED", "失败"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    job = models.ForeignKey(
        "exchange.ImportJob",
        related_name="items",
        on_delete=models.CASCADE,
        editable=False,
    )
    ordinal = models.PositiveIntegerField(editable=False)
    item_key = models.CharField(max_length=64, editable=False)
    item_path = models.CharField(max_length=512, editable=False)
    imported_article_id = models.CharField(max_length=26, null=True, editable=False)
    target_article_id = models.CharField(max_length=26, null=True, editable=False)
    planned_article_id = models.CharField(max_length=26, null=True, editable=False)
    detected_title = models.CharField(max_length=255, blank=True, editable=False)
    parse_status = models.CharField(
        max_length=12,
        choices=ParseStatus.choices,
        editable=False,
    )
    classification = models.CharField(
        max_length=24,
        choices=Classification.choices,
        null=True,
        editable=False,
    )
    decision = models.CharField(
        max_length=12,
        choices=Decision.choices,
        null=True,
        editable=False,
    )
    included = models.BooleanField(default=True, editable=False)
    mapped_section_id = models.UUIDField(null=True, editable=False)
    mapped_tag_ids = models.JSONField(default=list, editable=False)
    proposed_tag_names = models.JSONField(default=list, editable=False)
    conflict_summary = models.JSONField(default=dict, editable=False)
    front_matter = models.JSONField(default=dict, editable=False)
    body_markdown = models.TextField(blank=True, editable=False)
    preview_html = models.TextField(blank=True, editable=False)
    image_manifest = models.JSONField(default=list, editable=False)
    parse_error_code = models.CharField(max_length=96, blank=True, editable=False)
    result_status = models.CharField(
        max_length=12,
        choices=ResultStatus.choices,
        default=ResultStatus.PENDING,
        editable=False,
    )
    result_reason_code = models.CharField(max_length=96, blank=True, editable=False)
    result_article_id = models.CharField(max_length=26, null=True, editable=False)
    result_revision_id = models.CharField(max_length=26, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "exchange_import_item"
        ordering = ("job_id", "ordinal")
        constraints = [
            models.UniqueConstraint(
                fields=("job", "ordinal"),
                name="exchange_import_item_ordinal_unique",
            ),
            models.UniqueConstraint(
                fields=("job", "item_key"),
                name="exchange_import_item_key_unique",
            ),
            models.UniqueConstraint(
                fields=("job", "item_path"),
                name="exchange_import_item_path_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(ordinal__gte=1),
                name="exchange_import_item_ordinal_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(parse_status="VALID", parse_error_code="")
                    | models.Q(parse_status="INVALID") & ~models.Q(parse_error_code="")
                ),
                name="exchange_import_item_parse_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(classification__isnull=True, decision__isnull=True)
                    | models.Q(
                        classification__in=("INVALID", "FOREIGN_CONFLICT"),
                        decision="SKIP",
                        included=False,
                    )
                    | models.Q(
                        classification__in=("NEW", "TITLE_WARNING"),
                        decision__in=("SKIP", "CREATE"),
                    )
                    | models.Q(
                        classification="DUPLICATE_ID",
                        decision__in=("SKIP", "UPDATE", "CREATE"),
                    )
                ),
                name="exchange_import_item_decision_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        classification="DUPLICATE_ID",
                        target_article_id__isnull=False,
                    )
                    | ~models.Q(classification="DUPLICATE_ID")
                    & models.Q(target_article_id__isnull=True)
                ),
                name="exchange_import_item_target_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(planned_article_id__isnull=True)
                    | models.Q(decision="CREATE", included=True)
                ),
                name="exchange_import_item_planned_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        result_status="PENDING",
                        result_reason_code="",
                        result_article_id__isnull=True,
                        result_revision_id__isnull=True,
                    )
                    | models.Q(
                        result_status__in=("SKIPPED", "FAILED"),
                        result_article_id__isnull=True,
                        result_revision_id__isnull=True,
                    )
                    & ~models.Q(result_reason_code="")
                    | models.Q(
                        result_status="SUCCESS",
                        result_article_id__isnull=False,
                        result_revision_id__isnull=False,
                    )
                    & ~models.Q(result_reason_code="")
                ),
                name="exchange_import_item_result_shape",
            ),
        ]
