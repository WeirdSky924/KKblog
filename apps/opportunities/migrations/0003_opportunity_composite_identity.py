import unicodedata
from hashlib import sha256

from django.db import migrations, models
from django.db.models import Count


def _identity_title(value):
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _identity_key(normalized_url, normalized_title):
    return sha256(
        f"{len(normalized_url)}:{normalized_url}{normalized_title}".encode()
    ).hexdigest()


def backfill_identity_titles(apps, schema_editor):
    opportunity = apps.get_model("opportunities", "Opportunity")
    rows = []
    queryset = opportunity.objects.only(
        "id",
        "title",
        "normalized_target_url",
    ).iterator(chunk_size=500)
    for row in queryset:
        row.normalized_identity_title = _identity_title(row.title)
        row.identity_key = _identity_key(
            row.normalized_target_url,
            row.normalized_identity_title,
        )
        rows.append(row)
        if len(rows) == 500:
            opportunity.objects.bulk_update(
                rows,
                ("normalized_identity_title", "identity_key"),
                batch_size=500,
            )
            rows.clear()
    if rows:
        opportunity.objects.bulk_update(
            rows,
            ("normalized_identity_title", "identity_key"),
            batch_size=500,
        )

    duplicate = (
        opportunity.objects.values(
            "source_id",
            "identity_key",
        )
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .exists()
    )
    if duplicate:
        raise RuntimeError("Duplicate opportunity composite identity")


class Migration(migrations.Migration):
    dependencies = [("opportunities", "0002_opportunity_check_runtime")]

    operations = [
        migrations.AddField(
            model_name="opportunity",
            name="normalized_identity_title",
            field=models.CharField(default="", editable=False, max_length=600),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="opportunity",
            name="identity_key",
            field=models.CharField(default="", editable=False, max_length=64),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_identity_titles, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="opportunity",
            name="opp_source_url_unique",
        ),
        migrations.AddConstraint(
            model_name="opportunity",
            constraint=models.UniqueConstraint(
                fields=("source", "identity_key"),
                name="opp_source_identity_unique",
            ),
        ),
    ]
