import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_account_attachment_upload_enabled"),
        ("content", "0012_articlerevision_attachment_asset_id"),
        ("discovery", "0003_reading_bookmark"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticleLike",
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
                "db_table": "discovery_article_like",
                "indexes": [
                    models.Index(
                        fields=["article", "created_at"],
                        name="discovery_like_count_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("account", "article"),
                        name="discovery_article_like_account_article_unique",
                    )
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE discovery_article_like
                ADD CONSTRAINT discovery_article_like_account_fk
                FOREIGN KEY (account_id) REFERENCES account(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
                ALTER TABLE discovery_article_like
                DROP CONSTRAINT discovery_article_like_account_fk
            """,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE discovery_article_like
                ADD CONSTRAINT discovery_article_like_article_fk
                FOREIGN KEY (article_id) REFERENCES article(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
                ALTER TABLE discovery_article_like
                DROP CONSTRAINT discovery_article_like_article_fk
            """,
        ),
    ]
