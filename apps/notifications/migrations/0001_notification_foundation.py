import django.db.models.deletion
from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    initial = True
    dependencies = [("accounts", "0001_accounts_foundation")]

    operations = [
        migrations.CreateModel(
            name="Notification",
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
                ("template_key", models.CharField(editable=False, max_length=96)),
                ("target_type", models.CharField(editable=False, max_length=64)),
                ("target_id", models.CharField(editable=False, max_length=128)),
                ("payload_safe", models.JSONField(default=dict, editable=False)),
                (
                    "dedupe_key",
                    models.CharField(
                        blank=True, editable=False, max_length=255, null=True
                    ),
                ),
                (
                    "hidden_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notifications_acted",
                        to="accounts.account",
                    ),
                ),
            ],
            options={"db_table": "notification", "ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="NotificationReceipt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipts",
                        to="notifications.notification",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_receipts",
                        to="accounts.account",
                    ),
                ),
            ],
            options={"db_table": "notification_receipt"},
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("dedupe_key__isnull", False)),
                fields=("dedupe_key",),
                name="notification_dedupe_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="notificationreceipt",
            constraint=models.UniqueConstraint(
                fields=("notification", "recipient"), name="notification_receipt_unique"
            ),
        ),
        migrations.AddIndex(
            model_name="notificationreceipt",
            index=models.Index(
                condition=models.Q(("read_at__isnull", True)),
                fields=["recipient", "read_at", "notification"],
                name="notification_unread_idx",
            ),
        ),
    ]
