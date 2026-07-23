from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_ulid


class ImmutableRevisionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("文章修订不可原地更新。")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("文章修订不可原地更新。")

    def delete(self):
        raise ValidationError("文章修订不能单独删除。")


class ArticleRevision(models.Model):
    class ContentFormat(models.TextChoices):
        MARKDOWN = "MARKDOWN", "Markdown"
        TIPTAP_JSON = "TIPTAP_JSON", "富文本"

    class SummaryMode(models.TextChoices):
        NONE = "NONE", "不显示"
        AUTO = "AUTO", "自动摘要"
        CUSTOM = "CUSTOM", "自定义"

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "大众"
        AUTHENTICATED = "AUTHENTICATED", "登录可见"
        PRIVATE = "PRIVATE", "私人"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    article = models.ForeignKey(
        "content.Article",
        related_name="revisions",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    sequence = models.PositiveBigIntegerField()
    based_on = models.ForeignKey(
        "self",
        related_name="derived_revisions",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    restore_source = models.ForeignKey(
        "self",
        related_name="restored_revisions",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    content_format = models.CharField(max_length=16, choices=ContentFormat.choices)
    title = models.CharField(max_length=30)
    body_markdown = models.TextField(null=True, blank=True)
    body_tiptap = models.JSONField(null=True, blank=True)
    summary_mode = models.CharField(
        max_length=16,
        choices=SummaryMode.choices,
        default=SummaryMode.AUTO,
    )
    custom_summary = models.CharField(max_length=100, null=True, blank=True)
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    section = models.ForeignKey(
        "content.Section",
        related_name="revisions",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        blank=True,
    )
    cover_asset_id = models.CharField(max_length=26, null=True, blank=True)
    comments_enabled = models.BooleanField(default=True)
    comments_view_login = models.BooleanField(default=False)
    comments_post_login = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        "accounts.Account",
        related_name="article_revisions_created",
        on_delete=models.PROTECT,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableRevisionQuerySet.as_manager()

    class Meta:
        db_table = "article_revision"
        ordering = ("article_id", "sequence")
        indexes = [
            GinIndex(
                fields=("title",),
                name="article_rev_title_trgm_gin",
                opclasses=("gin_trgm_ops",),
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("article", "sequence"),
                name="article_revision_sequence_unique",
            ),
            models.UniqueConstraint(
                fields=("article", "id"),
                name="article_revision_article_id_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gte=1),
                name="article_revision_sequence_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(title=""),
                name="article_revision_title_nonempty",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        content_format="MARKDOWN",
                        body_markdown__isnull=False,
                        body_tiptap__isnull=True,
                    )
                    | models.Q(
                        content_format="TIPTAP_JSON",
                        body_markdown__isnull=True,
                        body_tiptap__isnull=False,
                    )
                ),
                name="article_revision_body_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        summary_mode="CUSTOM",
                        custom_summary__isnull=False,
                    )
                    | (
                        ~models.Q(summary_mode="CUSTOM")
                        & models.Q(custom_summary__isnull=True)
                    )
                ),
                name="article_revision_summary_shape",
            ),
        ]

    def clean(self) -> None:
        if self.based_on_id and self.based_on.article_id != self.article_id:
            raise ValidationError({"based_on": "编辑基线必须属于同一篇文章。"})
        if self.restore_source_id and self.restore_source.article_id != self.article_id:
            raise ValidationError({"restore_source": "恢复来源必须属于同一篇文章。"})

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("文章修订不可原地更新。")
        self.full_clean(validate_unique=False, validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("文章修订不能单独删除。")
