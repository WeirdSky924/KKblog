from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0013_articlerevision_tiptap_schema_version"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="tag",
            name="content_tag_live_name_unique",
        ),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(
                condition=models.Q(state__in=("PENDING", "ACTIVE")),
                fields=("normalized_name",),
                name="content_tag_live_name_unique",
            ),
        ),
    ]
