from django.db import models

from apps.core.ids import new_ulid


class Notification(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    template_key = models.CharField(max_length=96, editable=False)
    actor = models.ForeignKey(
        "accounts.Account",
        related_name="notifications_acted",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    target_type = models.CharField(max_length=64, editable=False)
    target_id = models.CharField(max_length=128, editable=False)
    payload_safe = models.JSONField(default=dict, editable=False)
    dedupe_key = models.CharField(max_length=255, null=True, blank=True, editable=False)
    hidden_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "notification"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("dedupe_key",),
                condition=models.Q(dedupe_key__isnull=False),
                name="notification_dedupe_unique",
            )
        ]


class NotificationReceipt(models.Model):
    notification = models.ForeignKey(
        Notification, related_name="receipts", on_delete=models.CASCADE
    )
    recipient = models.ForeignKey(
        "accounts.Account",
        related_name="notification_receipts",
        on_delete=models.CASCADE,
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "notification_receipt"
        constraints = [
            models.UniqueConstraint(
                fields=("notification", "recipient"),
                name="notification_receipt_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("recipient", "read_at", "notification"),
                name="notification_unread_idx",
                condition=models.Q(read_at__isnull=True),
            )
        ]
