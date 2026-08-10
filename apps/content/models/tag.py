import unicodedata

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_ulid, new_uuid


def normalize_tag_name(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValidationError("标签名称不合法。")
    display = unicodedata.normalize("NFKC", value).strip()
    if not display or len(display) > 50 or any(ord(char) < 32 for char in display):
        raise ValidationError("标签名称须为 1 至 50 个字符。")
    return display, display.casefold()


class Tag(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "待审核"
        ACTIVE = "ACTIVE", "全站可用"
        REJECTED = "REJECTED", "已驳回"
        DELETED = "DELETED", "已删除"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    name = models.CharField(max_length=50)
    normalized_name = models.CharField(max_length=50, editable=False)
    state = models.CharField(max_length=16, choices=State.choices)
    proposed_by = models.ForeignKey(
        "accounts.Account",
        related_name="tags_proposed",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    reviewed_by = models.ForeignKey(
        "accounts.Account",
        related_name="tags_reviewed",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "content_tag"
        ordering = ("normalized_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("normalized_name",),
                name="content_tag_name_unique",
            )
        ]

    def clean(self) -> None:
        self.name, self.normalized_name = normalize_tag_name(self.name)

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)


class RevisionTag(models.Model):
    revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="tag_snapshots",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    tag = models.ForeignKey(
        Tag,
        related_name="revision_snapshots",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "content_revision_tag"
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "tag"),
                name="content_revision_tag_unique",
            )
        ]


class ArticleTag(models.Model):
    article = models.ForeignKey(
        "content.Article",
        related_name="current_tags",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    tag = models.ForeignKey(
        Tag,
        related_name="current_articles",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "content_article_tag"
        constraints = [
            models.UniqueConstraint(
                fields=("article", "tag"),
                name="content_article_tag_unique",
            )
        ]
        indexes = [
            models.Index(fields=("tag", "article"), name="content_tag_article_idx")
        ]


class TagAssociationHistory(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    tag = models.ForeignKey(
        Tag,
        related_name="association_history",
        on_delete=models.PROTECT,
    )
    article_id = models.CharField(max_length=26, editable=False)
    removed_at = models.DateTimeField(editable=False)
    restored_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "content_tag_association_history"
        constraints = [
            models.UniqueConstraint(
                fields=("tag", "article_id"),
                name="content_tag_history_unique",
            )
        ]


class TagRestoreConflict(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    tag = models.ForeignKey(
        Tag,
        related_name="restore_conflicts",
        on_delete=models.PROTECT,
    )
    article_id = models.CharField(max_length=26, editable=False)
    reason = models.CharField(max_length=32, default="MAX_TAGS", editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "content_tag_restore_conflict"
        constraints = [
            models.UniqueConstraint(
                fields=("tag", "article_id"),
                condition=models.Q(resolved_at__isnull=True),
                name="content_tag_open_conflict_unique",
            )
        ]
