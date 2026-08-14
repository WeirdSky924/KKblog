from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("navigation", "0004_navigation_group_nodes"),
    ]

    operations = [
        migrations.AddField(
            model_name="navigationnode",
            name="default_expanded",
            field=models.BooleanField(default=False),
        ),
    ]
