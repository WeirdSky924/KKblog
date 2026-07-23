from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.ids import new_ulid


def default_edit_expiry():
    return timezone.now() + timedelta(hours=12)


class ArticleEditGrant(models.Model):
    class State(models.TextChoices):
        ACTIVE = "ACTIVE", "可编辑"
        CONFLICT = "CONFLICT", "冲突"
        CONSUMED = "CONSUMED", "已消费"
        REPLACED = "REPLACED", "已替换"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    article = models.ForeignKey(
        "content.Article",
        related_name="edit_grants",
        on_delete=models.CASCADE,
        editable=False,
    )
    baseline_revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="edit_grants",
        on_delete=models.CASCADE,
        editable=False,
    )
    actor = models.ForeignKey(
        "accounts.Account",
        related_name="article_edit_grants",
        on_delete=models.PROTECT,
        editable=False,
    )
    row_version = models.PositiveBigIntegerField(editable=False)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.ACTIVE,
        editable=False,
    )
    expires_at = models.DateTimeField(default=default_edit_expiry, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "content_article_edit_grant"
        indexes = [
            models.Index(
                fields=("article", "state", "expires_at"),
                name="content_edit_state_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(token_digest__regex=r"^[0-9a-f]{64}$"),
                name="content_edit_digest_shape",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="content_edit_expiry_after_create",
            ),
        ]
