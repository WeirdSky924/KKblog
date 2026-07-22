from django.db import models

from apps.accounts.deletion import AuthorArticleDecision
from apps.core.ids import new_ulid


class AccountDeletion(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    account_id = models.UUIDField(unique=True, editable=False)
    was_author = models.BooleanField(editable=False)
    author_disposition = models.CharField(
        max_length=24,
        choices=[(item.value, item.value) for item in AuthorArticleDecision],
        editable=False,
    )
    disposition_id = models.CharField(
        max_length=26, null=True, blank=True, editable=False
    )
    article_count = models.PositiveIntegerField(default=0, editable=False)
    deleted_by_id = models.UUIDField(editable=False)
    deleted_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "account_deletion"
        ordering = ("-deleted_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        author_disposition__in=(
                            AuthorArticleDecision.NO_ARTICLES,
                            AuthorArticleDecision.DELETE_ALL,
                            AuthorArticleDecision.EXPORT_THEN_DELETE,
                        ),
                        disposition_id__isnull=False,
                    )
                ),
                name="account_deletion_disposition_shape",
            )
        ]
