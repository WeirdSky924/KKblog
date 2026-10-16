from django.db import models

from apps.comments.constants import (
    GUESTBOOK_DEFAULT_ACCOUNT_DAILY_LIMIT,
    GUESTBOOK_DEFAULT_DAILY_LIMIT,
    GUESTBOOK_MAX_ACCOUNT_DAILY_LIMIT,
    GUESTBOOK_MAX_DAILY_LIMIT,
)
from apps.comments.targets import GUESTBOOK_TARGET_ID, DiscussionTargetType
from apps.core.ids import new_uuid


class DiscussionThread(models.Model):
    class TargetType(models.TextChoices):
        ARTICLE = DiscussionTargetType.ARTICLE.value, "文章"
        GUESTBOOK = DiscussionTargetType.GUESTBOOK.value, "留言板"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    target_id = models.CharField(max_length=26)
    owner = models.ForeignKey(
        "accounts.Account",
        related_name="discussion_threads_owned",
        on_delete=models.PROTECT,
    )
    comments_enabled = models.BooleanField(default=True)
    view_login_required = models.BooleanField(default=False)
    post_login_required = models.BooleanField(default=False)
    guestbook_daily_limit = models.PositiveSmallIntegerField(
        default=GUESTBOOK_DEFAULT_DAILY_LIMIT
    )
    guestbook_account_daily_limit = models.PositiveSmallIntegerField(
        default=GUESTBOOK_DEFAULT_ACCOUNT_DAILY_LIMIT
    )
    guestbook_quota_version = models.PositiveBigIntegerField(
        default=1,
        editable=False,
    )
    settings_revision_id = models.CharField(
        max_length=26,
        null=True,
        blank=True,
        editable=False,
    )
    deep_thread_alerted_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "discussion_thread"
        constraints = [
            models.UniqueConstraint(
                fields=("target_type", "target_id"),
                name="discussion_thread_target_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        target_type="ARTICLE",
                        target_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$",
                    )
                    | models.Q(
                        target_type="GUESTBOOK",
                        target_id=GUESTBOOK_TARGET_ID,
                    )
                ),
                name="discussion_thread_target_shape",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    guestbook_daily_limit__gte=1,
                    guestbook_daily_limit__lte=GUESTBOOK_MAX_DAILY_LIMIT,
                ),
                name="discussion_guestbook_daily_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    guestbook_account_daily_limit__gte=1,
                    guestbook_account_daily_limit__lte=GUESTBOOK_MAX_ACCOUNT_DAILY_LIMIT,
                ),
                name="discussion_guestbook_account_range",
            ),
            models.CheckConstraint(
                condition=models.Q(guestbook_quota_version__gte=1),
                name="discussion_guestbook_quota_version",
            ),
        ]
