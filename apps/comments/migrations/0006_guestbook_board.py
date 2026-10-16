import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_account_attachment_upload_enabled"),
        ("comments", "0005_comment_pin"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="guestbook_flag",
            field=models.CharField(
                choices=[
                    ("", "无标记"),
                    ("READ", "阅"),
                    ("NO", "否"),
                    ("DONE", "毕"),
                ],
                default="",
                max_length=4,
            ),
        ),
        migrations.AddField(
            model_name="comment",
            name="guestbook_hidden",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="comment",
            name="guestbook_hidden_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="comment",
            name="guestbook_hidden_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="guestbook_comments_hidden",
                to="accounts.account",
            ),
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(
                condition=models.Q(parent__isnull=True, state="VISIBLE"),
                fields=("thread", "guestbook_hidden", "-created_at", "-id"),
                name="comment_guestbook_public_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(
                condition=models.Q(parent__isnull=True),
                fields=("thread", "author", "created_at", "id"),
                name="comment_top_author_day_idx",
            ),
        ),
    ]
