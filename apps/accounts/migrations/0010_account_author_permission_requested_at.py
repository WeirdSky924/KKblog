from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_account_article_explanation_auto_accept")]

    operations = [
        migrations.AddField(
            model_name="account",
            name="author_permission_requested_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
