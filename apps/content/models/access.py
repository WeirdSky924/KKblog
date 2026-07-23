from django.db import models


class AdminArticleViewReceipt(models.Model):
    administrator = models.ForeignKey(
        "accounts.Account",
        related_name="admin_article_view_receipts",
        on_delete=models.PROTECT,
        editable=False,
    )
    author = models.ForeignKey(
        "accounts.Account",
        related_name="article_admin_view_receipts",
        on_delete=models.PROTECT,
        editable=False,
    )
    article = models.ForeignKey(
        "content.Article",
        related_name="admin_view_receipts",
        on_delete=models.CASCADE,
        editable=False,
    )
    view_date = models.DateField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "content_admin_article_view_receipt"
        constraints = [
            models.UniqueConstraint(
                fields=("administrator", "author", "article", "view_date"),
                name="content_admin_article_view_daily_unique",
            )
        ]
