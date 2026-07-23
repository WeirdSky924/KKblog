import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_nickname_history"),
        ("discovery", "0001_article_view_counter"),
    ]

    operations = [
        migrations.CreateModel(
            name="Bookmark",
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
                ("article_id", models.CharField(max_length=26)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "db_table": "discovery_bookmark",
                "ordering": ("-created_at", "-article_id"),
                "indexes": [
                    models.Index(
                        fields=["account", "-created_at", "article_id"],
                        name="discovery_bookmark_page_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("account", "article_id"),
                        name="discovery_bookmark_account_article_unique",
                    )
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE discovery_bookmark
                ADD CONSTRAINT discovery_bookmark_account_fk
                FOREIGN KEY (account_id) REFERENCES account(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
                ALTER TABLE discovery_bookmark
                DROP CONSTRAINT discovery_bookmark_account_fk
            """,
        ),
    ]
