from django.db import models

from apps.core.ids import new_ulid


class PublicationReviewGrant(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    article = models.ForeignKey(
        "content.Article",
        related_name="publication_review_grants",
        on_delete=models.CASCADE,
        editable=False,
    )
    revision = models.ForeignKey(
        "content.ArticleRevision",
        related_name="publication_review_grants",
        on_delete=models.CASCADE,
        editable=False,
    )
    actor = models.ForeignKey(
        "accounts.Account",
        related_name="publication_review_grants",
        on_delete=models.PROTECT,
        editable=False,
    )
    row_version = models.PositiveBigIntegerField(editable=False)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField(editable=False)
    consumed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "content_publication_review_grant"
        indexes = [
            models.Index(
                fields=("expires_at", "consumed_at"),
                name="content_review_expiry_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="content_review_expiry_after_create",
            ),
            models.CheckConstraint(
                condition=models.Q(token_digest__regex=r"^[0-9a-f]{64}$"),
                name="content_review_digest_shape",
            ),
        ]
