from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("comments", "0006_guestbook_board")]

    operations = [
        migrations.AddField(
            model_name="discussionthread",
            name="guestbook_daily_limit",
            field=models.PositiveSmallIntegerField(default=20),
        ),
        migrations.AddField(
            model_name="discussionthread",
            name="guestbook_account_daily_limit",
            field=models.PositiveSmallIntegerField(default=2),
        ),
        migrations.AddField(
            model_name="discussionthread",
            name="guestbook_quota_version",
            field=models.PositiveBigIntegerField(default=1, editable=False),
        ),
        migrations.AddConstraint(
            model_name="discussionthread",
            constraint=models.CheckConstraint(
                condition=models.Q(guestbook_daily_limit__gte=1)
                & models.Q(guestbook_daily_limit__lte=1_000),
                name="discussion_guestbook_daily_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="discussionthread",
            constraint=models.CheckConstraint(
                condition=models.Q(guestbook_account_daily_limit__gte=1)
                & models.Q(guestbook_account_daily_limit__lte=100),
                name="discussion_guestbook_account_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="discussionthread",
            constraint=models.CheckConstraint(
                condition=models.Q(guestbook_quota_version__gte=1),
                name="discussion_guestbook_quota_version",
            ),
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(
                condition=models.Q(parent__isnull=True),
                fields=("thread", "created_at"),
                name="comment_top_daily_idx",
            ),
        ),
    ]
