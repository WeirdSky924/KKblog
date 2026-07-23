from django.db import models


class ArticleViewCounter(models.Model):
    article = models.OneToOneField(
        "content.Article",
        primary_key=True,
        related_name="+",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    count = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "discovery_article_view_counter"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(count__gte=0),
                name="discovery_view_count_nonnegative",
            )
        ]
