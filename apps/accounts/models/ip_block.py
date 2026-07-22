from ipaddress import ip_address

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_ulid


class IpBlock(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    address = models.GenericIPAddressField(
        protocol="both", unpack_ipv4=True, editable=False
    )
    note = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        "accounts.Account",
        related_name="ip_blocks_created",
        on_delete=models.PROTECT,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    unblocked_by = models.ForeignKey(
        "accounts.Account",
        related_name="ip_blocks_removed",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        editable=False,
    )
    unblocked_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "account_ip_block"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("address",),
                condition=models.Q(unblocked_at__isnull=True),
                name="ip_block_active_addr_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("unblocked_at", "created_at"), name="ip_block_active_idx"
            ),
        ]

    def clean(self) -> None:
        try:
            parsed = ip_address(self.address)
        except ValueError:
            raise ValidationError({"address": "IP 地址无效"}) from None
        if getattr(parsed, "ipv4_mapped", None) is not None:
            parsed = parsed.ipv4_mapped
        self.address = str(parsed)
        if "\x00" in self.note:
            raise ValidationError({"note": "备注包含无效字符"})
