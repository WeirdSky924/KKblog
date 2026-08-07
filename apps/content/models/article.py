from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_ulid


class ArticleQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if "author" in kwargs or "author_id" in kwargs:
            raise ValidationError("文章作者不能转移。")
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if "author" in fields or "author_id" in fields:
            raise ValidationError("文章作者不能转移。")
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Article(models.Model):
    class PublicationState(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        SCHEDULED = "SCHEDULED", "定时"
        PUBLISHED = "PUBLISHED", "已发布"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    author = models.ForeignKey(
        "accounts.Account",
        related_name="articles",
        on_delete=models.PROTECT,
        editable=False,
    )
    publication_state = models.CharField(
        max_length=16,
        choices=PublicationState.choices,
        default=PublicationState.DRAFT,
    )
    working_revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="working_for_articles",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    published_revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="published_for_articles",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    scheduled_revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="scheduled_for_articles",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_published_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    purge_after = models.DateTimeField(null=True, blank=True)
    row_version = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        db_table = "article"
        indexes = [
            models.Index(
                fields=("author", "-updated_at"),
                name="article_author_updated_idx",
            ),
            models.Index(
                fields=("scheduled_for", "id"),
                condition=models.Q(publication_state="SCHEDULED", deleted_at=None),
                name="article_schedule_due_idx",
            ),
            models.Index(
                fields=("purge_after", "id"),
                condition=models.Q(purge_after__isnull=False),
                name="article_purge_due_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(deleted_at__isnull=True, purge_after__isnull=True)
                    | models.Q(
                        deleted_at__isnull=False,
                        purge_after__isnull=False,
                        purge_after__gt=models.F("deleted_at"),
                    )
                ),
                name="article_deletion_times_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        publication_state="SCHEDULED",
                        scheduled_revision__isnull=False,
                        scheduled_for__isnull=False,
                        scheduled_at__isnull=False,
                    )
                    | (
                        ~models.Q(publication_state="SCHEDULED")
                        & models.Q(
                            scheduled_revision__isnull=True,
                            scheduled_for__isnull=True,
                            scheduled_at__isnull=True,
                        )
                    )
                ),
                name="article_schedule_shape",
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            original_author = type(self).objects.only("author_id").get(pk=self.pk)
            if original_author.author_id != self.author_id:
                raise ValidationError("文章作者不能转移。")
        super().save(*args, **kwargs)

    @property
    def latest_published_at(self) -> datetime | None:
        return self.last_published_at or self.published_at
