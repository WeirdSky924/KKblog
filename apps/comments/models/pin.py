from django.db import models
from django.utils import timezone


class CommentPin(models.Model):
    thread = models.ForeignKey(
        "comments.DiscussionThread",
        related_name="+",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    comment = models.ForeignKey(
        "comments.Comment",
        related_name="+",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    pinned_by = models.ForeignKey(
        "accounts.Account",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
    )
    pinned_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "comment_pin"
        constraints = [
            models.UniqueConstraint(
                fields=("thread",),
                name="comment_pin_thread_unique",
            ),
            models.UniqueConstraint(
                fields=("comment",),
                name="comment_pin_comment_unique",
            ),
        ]
