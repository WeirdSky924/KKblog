from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opportunities", "0004_opportunity_default_filters"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunity",
            name="published_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddIndex(
            model_name="opportunity",
            index=models.Index(
                fields=["-published_at", "id"],
                name="opp_publication_time_idx",
            ),
        ),
    ]
