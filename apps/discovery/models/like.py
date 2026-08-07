from django.db import models


class ArticleLike(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "discovery_article_like"
        constraints = [
            models.UniqueConstraint(
                fields=("account", "article"),
                name="discovery_article_like_account_article_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("article", "created_at"),
                name="discovery_like_count_idx",
            )
        ]
