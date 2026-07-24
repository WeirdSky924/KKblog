from django.db import models


class ReportRecoverySnapshot(models.Model):
    class PreviousState(models.TextChoices):
        BUFFERED = "BUFFERED", "缓冲中"
        VISIBLE = "VISIBLE", "已公开"

    report = models.OneToOneField(
        "moderation.Report",
        primary_key=True,
        related_name="recovery_snapshot",
        on_delete=models.CASCADE,
    )
    comment_id = models.CharField(max_length=26)
    body = models.CharField(max_length=100)
    previous_state = models.CharField(max_length=16, choices=PreviousState.choices)
    previous_visible_at = models.DateTimeField()
    image_count = models.PositiveSmallIntegerField(default=0)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "moderation_report_recovery_snapshot"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(comment_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="moderation_recovery_comment_shape",
            ),
            models.CheckConstraint(
                condition=~models.Q(body=""),
                name="moderation_recovery_body_present",
            ),
            models.CheckConstraint(
                condition=models.Q(previous_state__in=("BUFFERED", "VISIBLE")),
                name="moderation_recovery_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(image_count__lte=3),
                name="moderation_recovery_image_count",
            ),
        ]
