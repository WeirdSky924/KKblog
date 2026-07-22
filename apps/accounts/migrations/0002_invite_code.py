import django.db.models.deletion
from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_accounts_foundation")]

    operations = [
        migrations.CreateModel(
            name="InviteCode",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.ids.new_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "code_digest",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                ("display_suffix", models.CharField(editable=False, max_length=4)),
                ("expires_at", models.DateTimeField(editable=False)),
                (
                    "revoked_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                (
                    "redeemed_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                ("created_at", models.DateTimeField(editable=False)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_invites",
                        to="accounts.account",
                    ),
                ),
                (
                    "redeemed_by",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="redeemed_invite",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "db_table": "account_invite_code",
                "indexes": [
                    models.Index(fields=["-created_at"], name="invite_created_idx"),
                    models.Index(fields=["expires_at"], name="invite_expires_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="invitecode",
            constraint=models.CheckConstraint(
                condition=models.Q(("expires_at__gt", models.F("created_at"))),
                name="invite_positive_lifetime",
            ),
        ),
        migrations.AddConstraint(
            model_name="invitecode",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("redeemed_at__isnull", True), ("redeemed_by__isnull", True)
                    ),
                    models.Q(
                        ("redeemed_at__isnull", False), ("redeemed_by__isnull", False)
                    ),
                    _connector="OR",
                ),
                name="invite_redemption_pair",
            ),
        ),
    ]
