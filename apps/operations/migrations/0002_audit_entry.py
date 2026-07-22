from django.db import migrations, models

import apps.core.ids


class Migration(migrations.Migration):
    dependencies = [("operations", "0001_task_run")]

    operations = [
        migrations.CreateModel(
            name="AuditEntry",
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
                ("trace_code", models.CharField(editable=False, max_length=30)),
                ("actor_id", models.UUIDField(editable=False)),
                ("action", models.CharField(editable=False, max_length=96)),
                ("target_type", models.CharField(editable=False, max_length=64)),
                ("target_id", models.CharField(editable=False, max_length=128)),
                (
                    "client_ip",
                    models.GenericIPAddressField(editable=False, unpack_ipv4=True),
                ),
                (
                    "summary",
                    models.CharField(blank=True, editable=False, max_length=255),
                ),
                ("before_safe", models.JSONField(default=dict, editable=False)),
                ("after_safe", models.JSONField(default=dict, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
            ],
            options={
                "db_table": "operations_audit_entry",
                "ordering": ("-created_at", "-id"),
                "indexes": [
                    models.Index(fields=["created_at"], name="audit_created_idx"),
                    models.Index(
                        fields=["action", "created_at"], name="audit_action_idx"
                    ),
                    models.Index(
                        fields=["target_type", "target_id"], name="audit_target_idx"
                    ),
                ],
            },
        )
    ]
