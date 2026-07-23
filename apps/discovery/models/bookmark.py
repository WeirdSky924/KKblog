from django.db import models


class Bookmark(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        related_name="+",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    article_id = models.CharField(max_length=26)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "discovery_bookmark"
        ordering = ("-created_at", "-article_id")
        constraints = [
            models.UniqueConstraint(
                fields=("account", "article_id"),
                name="discovery_bookmark_account_article_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("account", "-created_at", "article_id"),
                name="discovery_bookmark_page_idx",
            )
        ]
