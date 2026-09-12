from django.db import models

from apps.core.ids import new_ulid


class ArticleExplanationRequest(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "等待中"
        RUNNING = "RUNNING", "生成中"
        SUCCEEDED = "SUCCEEDED", "已完成"
        FAILED = "FAILED", "失败"
        CANCELLED = "CANCELLED", "已停止"

    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    account = models.ForeignKey(
        "accounts.Account",
        related_name="article_explanation_requests",
        on_delete=models.PROTECT,
        editable=False,
    )
    article_id = models.CharField(max_length=26, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True, editable=False)
    usage_id = models.CharField(max_length=26, unique=True, editable=False)
    task_run_id = models.CharField(max_length=26, unique=True, blank=True, null=True)
    invocation_id = models.CharField(
        max_length=26, unique=True, blank=True, null=True, editable=False
    )
    selected_text = models.TextField(editable=False)
    article_title = models.CharField(max_length=30, editable=False)
    article_summary = models.CharField(max_length=100, blank=True, editable=False)
    article_tags = models.JSONField(default=list, editable=False)
    section_heading = models.CharField(max_length=255, blank=True, editable=False)
    original_char_count = models.PositiveIntegerField(editable=False)
    processed_char_count = models.PositiveIntegerField(editable=False)
    was_truncated = models.BooleanField(default=False, editable=False)
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.PENDING,
        editable=False,
    )
    result_markdown = models.TextField(blank=True, default="", editable=False)
    safe_error_code = models.CharField(max_length=96, blank=True, default="")
    safe_error_message = models.CharField(max_length=255, blank=True, default="")
    retryable = models.BooleanField(default=False, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "discovery_article_explanation_request"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state__in=("PENDING", "RUNNING"),
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        state__in=("SUCCEEDED", "FAILED", "CANCELLED"),
                        completed_at__isnull=False,
                    )
                ),
                name="article_explanation_request_completion_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state="SUCCEEDED", result_markdown__gt="")
                    | ~models.Q(state="SUCCEEDED")
                ),
                name="article_explanation_request_success_result_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account", "created_at"),
                name="aex_req_account_idx",
            ),
            models.Index(
                fields=("state", "created_at"),
                name="aex_req_state_idx",
            ),
        ]
