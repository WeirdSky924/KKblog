from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0010_article_revision_title_trgm")]

    operations = [
        migrations.AddField(
            model_name="articlerevision",
            name="reason",
            field=models.CharField(
                choices=[
                    ("STANDARD", "常规保存"),
                    ("IMPORT", "导入"),
                    ("IMPORT_FORMAT_CHANGE", "导入格式转换"),
                ],
                default="STANDARD",
                editable=False,
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="articlerevision",
            name="import_key",
            field=models.CharField(
                editable=False,
                max_length=128,
                null=True,
                unique=True,
            ),
        ),
    ]
