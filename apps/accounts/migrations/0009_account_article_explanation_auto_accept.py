from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_account_attachment_upload_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="article_explanation_auto_accept",
            field=models.BooleanField(default=False),
        ),
    ]
