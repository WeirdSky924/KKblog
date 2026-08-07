from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_account_attachment_upload_enabled"),
        ("content", "0012_articlerevision_attachment_asset_id"),
        ("discovery", "0002_bookmark"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingBookmark",
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
                ("revision_id", models.CharField(max_length=26)),
                (
                    "progress",
                    models.DecimalField(decimal_places=6, max_digits=7),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.account",
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="content.article",
                    ),
                ),
            ],
            options={
                "db_table": "discovery_reading_bookmark",
                "indexes": [
                    models.Index(
                        fields=["account", "-updated_at", "article"],
                        name="discovery_readmark_updated_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("account", "article"),
                        name=("discovery_reading_bookmark_account_article_unique"),
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            progress__gte=Decimal("0"),
                            progress__lte=Decimal("1"),
                        ),
                        name="discovery_reading_bookmark_progress_range",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE discovery_reading_bookmark
                ADD CONSTRAINT discovery_reading_bookmark_account_fk
                FOREIGN KEY (account_id) REFERENCES account(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
                ALTER TABLE discovery_reading_bookmark
                DROP CONSTRAINT discovery_reading_bookmark_account_fk
            """,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE discovery_reading_bookmark
                ADD CONSTRAINT discovery_reading_bookmark_article_fk
                FOREIGN KEY (article_id) REFERENCES article(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
                ALTER TABLE discovery_reading_bookmark
                DROP CONSTRAINT discovery_reading_bookmark_article_fk
            """,
        ),
    ]
