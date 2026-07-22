import django.db.models.deletion
from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_invite_code")]

    operations = [
        migrations.CreateModel(
            name="SecurityEvent",
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
                ("event_type", models.CharField(editable=False, max_length=64)),
                (
                    "subject_digest",
                    models.CharField(blank=True, editable=False, max_length=64),
                ),
                (
                    "client_ip",
                    models.GenericIPAddressField(editable=False, unpack_ipv4=True),
                ),
                ("trace_code", models.CharField(editable=False, max_length=30)),
                ("safe_summary", models.JSONField(default=dict, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                (
                    "account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="security_events",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "db_table": "account_security_event",
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(
                        fields=["event_type", "created_at"],
                        name="security_event_type_idx",
                    ),
                    models.Index(
                        fields=["account", "created_at"],
                        name="security_event_account_idx",
                    ),
                ],
            },
        )
    ]
