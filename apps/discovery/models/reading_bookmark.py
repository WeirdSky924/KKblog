from django.db import models


class ReadingBookmark(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        related_name="+",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    article = models.ForeignKey(
        "content.Article",
        related_name="+",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    revision_id = models.CharField(max_length=26)
    progress = models.DecimalField(max_digits=7, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "discovery_reading_bookmark"
        constraints = [
            models.UniqueConstraint(
                fields=("account", "article"),
                name="discovery_reading_bookmark_account_article_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(progress__gte=0, progress__lte=1),
                name="discovery_reading_bookmark_progress_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account", "-updated_at", "article"),
                name="discovery_readmark_updated_idx",
            )
        ]
