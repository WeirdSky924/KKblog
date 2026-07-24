from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0002_comment_created_at_clock"),
    ]

    operations = [
        migrations.AddField(
            model_name="discussionthread",
            name="deep_thread_alerted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
