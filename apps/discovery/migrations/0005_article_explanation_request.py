from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_account_article_explanation_auto_accept"),
        ("discovery", "0004_article_like"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticleExplanationRequest",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=apps.core.ids.new_ulid,
                        editable=False,
                        max_length=26,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "article_id",
                    models.CharField(editable=False, max_length=26),
                ),
                (
                    "idempotency_key",
                    models.CharField(editable=False, max_length=128, unique=True),
                ),
                (
                    "usage_id",
                    models.CharField(editable=False, max_length=26, unique=True),
                ),
                (
                    "task_run_id",
                    models.CharField(blank=True, max_length=26, null=True, unique=True),
                ),
                (
                    "invocation_id",
                    models.CharField(
                        blank=True,
                        editable=False,
                        max_length=26,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "selected_text",
                    models.TextField(editable=False),
                ),
                (
                    "article_title",
                    models.CharField(editable=False, max_length=30),
                ),
                (
                    "article_summary",
                    models.CharField(blank=True, editable=False, max_length=100),
                ),
                (
                    "article_tags",
                    models.JSONField(default=list, editable=False),
                ),
                (
                    "section_heading",
                    models.CharField(blank=True, editable=False, max_length=255),
                ),
                (
                    "original_char_count",
                    models.PositiveIntegerField(editable=False),
                ),
                (
                    "processed_char_count",
                    models.PositiveIntegerField(editable=False),
                ),
                (
                    "was_truncated",
                    models.BooleanField(default=False, editable=False),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("PENDING", "等待中"),
                            ("RUNNING", "生成中"),
                            ("SUCCEEDED", "已完成"),
                            ("FAILED", "失败"),
                            ("CANCELLED", "已停止"),
                        ],
                        default="PENDING",
                        editable=False,
                        max_length=16,
                    ),
                ),
                (
                    "result_markdown",
                    models.TextField(blank=True, default="", editable=False),
                ),
                (
                    "safe_error_code",
                    models.CharField(blank=True, default="", max_length=96),
                ),
                (
                    "safe_error_message",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "retryable",
                    models.BooleanField(default=False, editable=False),
                ),
                (
                    "completed_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, editable=False),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, editable=False),
                ),
                (
                    "account",
                    models.ForeignKey(
                        editable=False,
                        on_delete=models.PROTECT,
                        related_name="article_explanation_requests",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "db_table": "discovery_article_explanation_request",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.AddConstraint(
            model_name="articleexplanationrequest",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("completed_at__isnull", True),
                        ("state__in", ("PENDING", "RUNNING")),
                    )
                    | models.Q(
                        ("completed_at__isnull", False),
                        ("state__in", ("SUCCEEDED", "FAILED", "CANCELLED")),
                    )
                ),
                name="article_explanation_request_completion_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="articleexplanationrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("result_markdown__gt", ""), ("state", "SUCCEEDED")),
                    models.Q(("state", "SUCCEEDED"), _negated=True),
                    _connector="OR",
                ),
                name="article_explanation_request_success_result_shape",
            ),
        ),
        migrations.AddIndex(
            model_name="articleexplanationrequest",
            index=models.Index(
                fields=("account", "created_at"),
                name="aex_req_account_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="articleexplanationrequest",
            index=models.Index(
                fields=("state", "created_at"),
                name="aex_req_state_idx",
            ),
        ),
    ]
