from django.db import models
from django.utils import timezone

from apps.core.ids import new_uuid


class InviteCode(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    code_digest = models.CharField(max_length=64, unique=True, editable=False)
    display_suffix = models.CharField(max_length=4, editable=False)
    expires_at = models.DateTimeField(editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True, editable=False)
    redeemed_by = models.OneToOneField(
        "accounts.Account",
        related_name="redeemed_invite",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    redeemed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        "accounts.Account",
        related_name="created_invites",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "account_invite_code"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="invite_positive_lifetime",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(redeemed_by__isnull=True, redeemed_at__isnull=True)
                    | models.Q(redeemed_by__isnull=False, redeemed_at__isnull=False)
                ),
                name="invite_redemption_pair",
            ),
        ]
        indexes = [
            models.Index(fields=("-created_at",), name="invite_created_idx"),
            models.Index(fields=("expires_at",), name="invite_expires_idx"),
        ]

    def state(self, *, now=None) -> str:
        current = now or timezone.now()
        if self.redeemed_at is not None:
            return "USED"
        if self.revoked_at is not None:
            return "REVOKED"
        if self.expires_at <= current:
            return "EXPIRED"
        return "ACTIVE"
