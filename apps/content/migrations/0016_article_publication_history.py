import django.db.models.deletion
from django.db import migrations, models

import apps.core.ids

SAME_ARTICLE_CONSTRAINT = "content_publication_revision_same_article_fk"


def apply_deferred_schema(apps, schema_editor):
    deferred = tuple(schema_editor.deferred_sql)
    schema_editor.deferred_sql.clear()
    for statement in deferred:
        schema_editor.execute(statement)


def backfill_publication_history(apps, schema_editor):
    Article = apps.get_model("content", "Article")
    Publication = apps.get_model("content", "ArticlePublication")
    Revision = apps.get_model("content", "ArticleRevision")
    OutboxEvent = apps.get_model("core", "OutboxEvent")

    events = (
        OutboxEvent.objects.filter(
            event_type="article.published.v1",
            aggregate_type="article",
        )
        .order_by("occurred_at", "event_id")
        .values_list("aggregate_id", "payload", "occurred_at")
    )
    for article_id, payload, occurred_at in events.iterator(chunk_size=200):
        revision_id = payload.get("revision_id") if isinstance(payload, dict) else None
        if not isinstance(revision_id, str):
            continue
        if not Revision.objects.filter(
            pk=revision_id,
            article_id=article_id,
        ).exists():
            continue
        Publication.objects.get_or_create(
            article_id=article_id,
            revision_id=revision_id,
            defaults={"published_at": occurred_at},
        )

    articles = Article.objects.exclude(published_revision_id__isnull=True).values_list(
        "id",
        "published_revision_id",
        "published_at",
        "last_published_at",
    )
    for article_id, revision_id, published_at, last_published_at in articles.iterator(
        chunk_size=200
    ):
        revision = Revision.objects.filter(
            pk=revision_id,
            article_id=article_id,
        ).first()
        if revision is None:
            continue
        Publication.objects.get_or_create(
            article_id=article_id,
            revision_id=revision_id,
            defaults={
                "published_at": last_published_at
                or published_at
                or revision.created_at,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0015_merge_duplicate_tag_identities"),
        ("core", "0001_outbox_foundation"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticlePublication",
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
                ("published_at", models.DateTimeField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                (
                    "article",
                    models.ForeignKey(
                        db_constraint=False,
                        db_index=False,
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="publication_history",
                        to="content.article",
                    ),
                ),
                (
                    "revision",
                    models.ForeignKey(
                        db_constraint=False,
                        db_index=False,
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="publication_history",
                        to="content.articlerevision",
                    ),
                ),
            ],
            options={
                "db_table": "content_article_publication",
                "ordering": ("-published_at", "-id"),
            },
        ),
        migrations.AddConstraint(
            model_name="articlepublication",
            constraint=models.UniqueConstraint(
                fields=("article", "revision"),
                name="content_publication_article_revision_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="articlepublication",
            index=models.Index(
                fields=["article", "published_at"],
                name="content_pub_article_time_idx",
            ),
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE content_article_publication "
                f"ADD CONSTRAINT {SAME_ARTICLE_CONSTRAINT} "
                "FOREIGN KEY (article_id, revision_id) "
                "REFERENCES article_revision (article_id, id) "
                "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                "ALTER TABLE content_article_publication "
                f"DROP CONSTRAINT IF EXISTS {SAME_ARTICLE_CONSTRAINT}"
            ),
        ),
        migrations.RunPython(
            apply_deferred_schema,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            backfill_publication_history,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
