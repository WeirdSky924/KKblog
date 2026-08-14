from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_ulid


class ArticlePublication(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    article = models.ForeignKey(
        "content.Article",
        related_name="publication_history",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_index=False,
        editable=False,
    )
    revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="publication_history",
        on_delete=models.CASCADE,
        db_constraint=False,
        db_index=False,
        editable=False,
    )
    published_at = models.DateTimeField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "content_article_publication"
        ordering = ("-published_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("article", "revision"),
                name="content_publication_article_revision_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("article", "published_at"),
                name="content_pub_article_time_idx",
            )
        ]

    def clean(self) -> None:
        if self.revision_id and self.article_id:
            revision_article_id = getattr(self.revision, "article_id", None)
            if revision_article_id != self.article_id:
                raise ValidationError("发布记录的修订必须属于同一篇文章。")

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("文章发布记录不可原地更新。")
        self.full_clean(validate_unique=False, validate_constraints=False)
        super().save(*args, **kwargs)


__all__ = ["ArticlePublication"]
