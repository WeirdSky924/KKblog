from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_notification_foundation"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                condition=models.Q(
                    ("deleted_at__isnull", True),
                    ("hidden_at__isnull", True),
                ),
                fields=("-created_at", "-id"),
                name="notification_visible_time_idx",
            ),
        ),
    ]
