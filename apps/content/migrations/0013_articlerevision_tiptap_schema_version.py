from django.db import migrations, models


def backfill_legacy_tiptap_schema(apps, schema_editor) -> None:
    revision = apps.get_model("content", "ArticleRevision")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE article_revision DISABLE TRIGGER "
            "article_revision_immutable_trigger"
        )
    revision.objects.filter(content_format="TIPTAP_JSON").update(
        tiptap_schema_version=1
    )
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE article_revision ENABLE TRIGGER "
            "article_revision_immutable_trigger"
        )


def clear_tiptap_schema_version(apps, schema_editor) -> None:
    revision = apps.get_model("content", "ArticleRevision")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE article_revision DISABLE TRIGGER "
            "article_revision_immutable_trigger"
        )
    revision.objects.exclude(tiptap_schema_version=None).update(
        tiptap_schema_version=None
    )
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE article_revision ENABLE TRIGGER "
            "article_revision_immutable_trigger"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0012_articlerevision_attachment_asset_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="articlerevision",
            name="tiptap_schema_version",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(
            backfill_legacy_tiptap_schema,
            clear_tiptap_schema_version,
        ),
        migrations.AddConstraint(
            model_name="articlerevision",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        content_format="MARKDOWN",
                        tiptap_schema_version__isnull=True,
                    )
                    | models.Q(
                        content_format="TIPTAP_JSON",
                        tiptap_schema_version__isnull=False,
                        tiptap_schema_version__in=(1, 2),
                    )
                ),
                name="article_revision_tiptap_schema_shape",
            ),
        ),
    ]
