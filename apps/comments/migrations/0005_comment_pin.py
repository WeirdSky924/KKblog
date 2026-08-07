import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_account_attachment_upload_enabled"),
        ("comments", "0004_thread_settings_revision"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommentPin",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "pinned_at",
                    models.DateTimeField(default=timezone.now, editable=False),
                ),
                (
                    "comment",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="comments.comment",
                    ),
                ),
                (
                    "pinned_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="accounts.account",
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="comments.discussionthread",
                    ),
                ),
            ],
            options={
                "db_table": "comment_pin",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("thread",),
                        name="comment_pin_thread_unique",
                    ),
                    models.UniqueConstraint(
                        fields=("comment",),
                        name="comment_pin_comment_unique",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE comment_pin
                ADD CONSTRAINT comment_pin_thread_fk
                FOREIGN KEY (thread_id) REFERENCES discussion_thread(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

                ALTER TABLE comment_pin
                ADD CONSTRAINT comment_pin_comment_fk
                FOREIGN KEY (comment_id) REFERENCES comment(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

                ALTER TABLE comment_pin
                ADD CONSTRAINT comment_pin_pinned_by_fk
                FOREIGN KEY (pinned_by_id) REFERENCES account(id)
                ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
            """,
            reverse_sql="""
                ALTER TABLE comment_pin DROP CONSTRAINT comment_pin_pinned_by_fk;
                ALTER TABLE comment_pin DROP CONSTRAINT comment_pin_comment_fk;
                ALTER TABLE comment_pin DROP CONSTRAINT comment_pin_thread_fk;
            """,
        ),
    ]
