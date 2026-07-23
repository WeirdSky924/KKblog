from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("content", "0009_authorcontentmask_and_more")]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name="articlerevision",
            index=GinIndex(
                fields=("title",),
                name="article_rev_title_trgm_gin",
                opclasses=("gin_trgm_ops",),
            ),
        ),
    ]
