from django.db import models


class NicknameHistory(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="nickname_history",
    )
    previous_nickname = models.CharField(max_length=16, null=True, blank=True)
    nickname = models.CharField(max_length=16, null=True, blank=True)
    changed_at = models.DateTimeField()

    class Meta:
        db_table = "account_nickname_history"
        ordering = ("-changed_at", "-id")
        indexes = [
            models.Index(
                fields=("account", "changed_at"),
                name="nickname_history_account_idx",
            )
        ]
