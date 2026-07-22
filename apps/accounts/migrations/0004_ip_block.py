import django.db.models.deletion
from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_security_event")]

    operations = [
        migrations.CreateModel(
            name="IpBlock",
            fields=[
                (
                    "id",
                    models.CharField(
                        default=apps.core.ids.new_ulid,
                        editable=False,
                        max_length=26,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "address",
                    models.GenericIPAddressField(editable=False, unpack_ipv4=True),
                ),
                ("note", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "unblocked_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ip_blocks_created",
                        to="accounts.account",
                    ),
                ),
                (
                    "unblocked_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ip_blocks_removed",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "db_table": "account_ip_block",
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(
                        fields=["unblocked_at", "created_at"],
                        name="ip_block_active_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(unblocked_at__isnull=True),
                        fields=("address",),
                        name="ip_block_active_addr_uniq",
                    )
                ],
            },
        )
    ]
