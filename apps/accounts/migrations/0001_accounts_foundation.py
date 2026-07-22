import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("email", models.CharField(max_length=254)),
                ("password_hash", models.CharField(max_length=128)),
                ("nickname", models.CharField(blank=True, max_length=16, null=True)),
                (
                    "normalized_nickname",
                    models.TextField(blank=True, editable=False, null=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "启用"), ("DISABLED", "禁用")],
                        default="ACTIVE",
                        max_length=16,
                    ),
                ),
                (
                    "theme",
                    models.CharField(
                        choices=[
                            ("LIGHT", "浅色"),
                            ("DARK", "深色"),
                            ("EYE_CARE", "护眼"),
                        ],
                        default="LIGHT",
                        max_length=16,
                    ),
                ),
                (
                    "avatar_asset_id",
                    models.CharField(blank=True, max_length=26, null=True),
                ),
                ("nickname_changed_at", models.DateTimeField(blank=True, null=True)),
                ("must_change_password", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "account"},
        ),
        migrations.CreateModel(
            name="BootstrapState",
            fields=[
                (
                    "key",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("account_id", models.UUIDField(blank=True, null=True)),
            ],
            options={"db_table": "account_bootstrap_state"},
        ),
        migrations.CreateModel(
            name="LoginSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("STANDARD_12H", "12 小时"),
                            ("REMEMBER_30D", "30 天"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user_agent_summary", models.CharField(blank=True, max_length=255)),
                ("created_ip", models.GenericIPAddressField(unpack_ipv4=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="login_sessions",
                        to="accounts.account",
                    ),
                ),
            ],
            options={"db_table": "account_login_session"},
        ),
        migrations.CreateModel(
            name="RoleAssignment",
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
                (
                    "role",
                    models.CharField(
                        choices=[("AUTHOR", "作者"), ("ADMINISTRATOR", "管理员")],
                        max_length=20,
                    ),
                ),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="roles",
                        to="accounts.account",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="roles_granted",
                        to="accounts.account",
                    ),
                ),
            ],
            options={"db_table": "account_role_assignment"},
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                Lower("email"), name="account_email_ci_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                condition=models.Q(("normalized_nickname__isnull", False)),
                fields=("normalized_nickname",),
                name="account_nickname_casefold_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="loginsession",
            constraint=models.CheckConstraint(
                condition=models.Q(("expires_at__gt", models.F("created_at"))),
                name="login_session_positive_lifetime",
            ),
        ),
        migrations.AddIndex(
            model_name="loginsession",
            index=models.Index(
                fields=["account", "revoked_at", "expires_at"],
                name="login_session_active_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.UniqueConstraint(
                fields=("account", "role"), name="account_role_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "ADMINISTRATOR")),
                fields=("role",),
                name="one_administrator_role",
            ),
        ),
    ]
