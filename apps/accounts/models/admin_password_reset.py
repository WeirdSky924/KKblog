from django.db import models
from django.db.models import F


class AdminPasswordReset(models.Model):
    account = models.OneToOneField(
        "accounts.Account",
        primary_key=True,
        related_name="admin_password_reset",
        on_delete=models.CASCADE,
    )
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "account_admin_password_reset"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=F("created_at")),
                name="account_admin_pw_reset_positive_lifetime",
            )
        ]
