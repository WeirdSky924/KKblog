import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("content", "0010_article_revision_title_trgm")]

    operations = [
        migrations.CreateModel(
            name="ArticleViewCounter",
            fields=[
                (
                    "article",
                    models.OneToOneField(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="content.article",
                    ),
                ),
                ("count", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "discovery_article_view_counter",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("count__gte", 0)),
                        name="discovery_view_count_nonnegative",
                    )
                ],
            },
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE discovery_article_view_counter
                ADD CONSTRAINT discovery_view_article_fk
                FOREIGN KEY (article_id) REFERENCES article(id)
                ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
            """,
            reverse_sql="""
                ALTER TABLE discovery_article_view_counter
                DROP CONSTRAINT discovery_view_article_fk
            """,
        ),
    ]
