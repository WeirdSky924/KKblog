from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("comments", "0003_thread_deep_alert")]

    operations = [
        migrations.AddField(
            model_name="discussionthread",
            name="settings_revision_id",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=26,
                null=True,
            ),
        ),
    ]
