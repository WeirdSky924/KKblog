from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0016_article_publication_history"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="article",
            index=models.Index(
                condition=models.Q(
                    ("deleted_at__isnull", True),
                    ("publication_state", "PUBLISHED"),
                    ("published_at__isnull", False),
                ),
                fields=("-published_at", "-id"),
                name="article_public_listing_idx",
            ),
        ),
    ]
