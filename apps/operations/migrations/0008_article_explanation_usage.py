from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_account_article_explanation_auto_accept"),
        ("operations", "0007_task_run_cancelled"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticleExplanationUsage",
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
                    "idempotency_key",
                    models.CharField(editable=False, max_length=128, unique=True),
                ),
                (
                    "usage_date",
                    models.DateField(editable=False),
                ),
                (
                    "occurred_at",
                    models.DateTimeField(editable=False),
                ),
                (
                    "counts_toward_limit",
                    models.BooleanField(default=True, editable=False),
                ),
                (
                    "retry_allowed",
                    models.BooleanField(default=False, editable=False),
                ),
                (
                    "account",
                    models.ForeignKey(
                        editable=False,
                        on_delete=models.PROTECT,
                        related_name="article_explanation_usages",
                        to="accounts.account",
                    ),
                ),
                (
                    "retry_of",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=models.PROTECT,
                        related_name="retries",
                        to="operations.articleexplanationusage",
                    ),
                ),
            ],
            options={
                "db_table": "operations_article_explanation_usage",
                "ordering": ("-occurred_at", "-id"),
            },
        ),
        migrations.AddConstraint(
            model_name="articleexplanationusage",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("counts_toward_limit", True),
                        ("retry_of__isnull", True),
                    )
                    | models.Q(
                        ("counts_toward_limit", False),
                        ("retry_of__isnull", False),
                    )
                ),
                name="article_explanation_usage_retry_shape",
            ),
        ),
        migrations.AddIndex(
            model_name="articleexplanationusage",
            index=models.Index(
                fields=("account", "usage_date", "counts_toward_limit"),
                name="article_explain_usage_day_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="articleexplanationusage",
            index=models.Index(
                fields=("account", "occurred_at"),
                name="article_explain_usage_time_idx",
            ),
        ),
    ]
