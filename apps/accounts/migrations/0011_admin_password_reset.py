import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_account_author_permission_requested_at")]

    operations = [
        migrations.CreateModel(
            name="AdminPasswordReset",
            fields=[
                (
                    "account",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="admin_password_reset",
                        serialize=False,
                        to="accounts.account",
                    ),
                ),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "account_admin_password_reset",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(expires_at__gt=models.F("created_at")),
                        name="account_admin_pw_reset_positive_lifetime",
                    )
                ],
            },
        ),
    ]
