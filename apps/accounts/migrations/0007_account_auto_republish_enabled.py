from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_nickname_history")]

    operations = [
        migrations.AddField(
            model_name="account",
            name="auto_republish_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
