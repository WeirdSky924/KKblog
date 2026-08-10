from django.db import migrations, models
from django.db.models import Count

_STATE_PRIORITY = {
    "ACTIVE": 4,
    "PENDING": 3,
    "REJECTED": 2,
    "DELETED": 1,
}


def _merge_revision_tags(RevisionTag, *, canonical_id, duplicate_ids):
    revision_ids = tuple(
        RevisionTag.objects.filter(tag_id__in=duplicate_ids)
        .order_by("revision_id")
        .values_list("revision_id", flat=True)
        .distinct()
    )
    for revision_id in revision_ids:
        RevisionTag.objects.filter(
            revision_id=revision_id,
            tag_id__in=duplicate_ids,
        ).delete()
        RevisionTag.objects.get_or_create(
            revision_id=revision_id,
            tag_id=canonical_id,
        )


def _merge_article_tags(ArticleTag, *, canonical_id, duplicate_ids):
    article_ids = tuple(
        ArticleTag.objects.filter(tag_id__in=duplicate_ids)
        .order_by("article_id")
        .values_list("article_id", flat=True)
        .distinct()
    )
    for article_id in article_ids:
        ArticleTag.objects.filter(
            article_id=article_id,
            tag_id__in=duplicate_ids,
        ).delete()
        ArticleTag.objects.get_or_create(
            article_id=article_id,
            tag_id=canonical_id,
        )


def _merge_association_history(History, *, tag_ids, canonical_id):
    article_ids = tuple(
        History.objects.filter(tag_id__in=tag_ids)
        .order_by("article_id")
        .values_list("article_id", flat=True)
        .distinct()
    )
    for article_id in article_ids:
        histories = tuple(
            History.objects.filter(
                tag_id__in=tag_ids,
                article_id=article_id,
            ).order_by("-removed_at", "-id")
        )
        keeper = histories[0]
        History.objects.filter(pk__in=[item.pk for item in histories[1:]]).delete()
        if keeper.tag_id != canonical_id:
            keeper.tag_id = canonical_id
            keeper.save(update_fields=("tag",))


def _merge_restore_conflicts(Conflict, *, tag_ids, canonical_id):
    article_ids = tuple(
        Conflict.objects.filter(tag_id__in=tag_ids)
        .order_by("article_id")
        .values_list("article_id", flat=True)
        .distinct()
    )
    for article_id in article_ids:
        open_conflicts = tuple(
            Conflict.objects.filter(
                tag_id__in=tag_ids,
                article_id=article_id,
                resolved_at__isnull=True,
            ).order_by("created_at", "id")
        )
        if open_conflicts:
            keeper = open_conflicts[0]
            Conflict.objects.filter(
                pk__in=[item.pk for item in open_conflicts[1:]]
            ).delete()
            if keeper.tag_id != canonical_id:
                keeper.tag_id = canonical_id
                keeper.save(update_fields=("tag",))
        Conflict.objects.filter(
            tag_id__in=tag_ids,
            article_id=article_id,
            resolved_at__isnull=False,
        ).update(tag_id=canonical_id)


def merge_duplicate_tag_identities(apps, schema_editor):
    Tag = apps.get_model("content", "Tag")
    RevisionTag = apps.get_model("content", "RevisionTag")
    ArticleTag = apps.get_model("content", "ArticleTag")
    History = apps.get_model("content", "TagAssociationHistory")
    Conflict = apps.get_model("content", "TagRestoreConflict")
    AuditEntry = apps.get_model("operations", "AuditEntry")
    Notification = apps.get_model("notifications", "Notification")

    duplicate_names = tuple(
        Tag.objects.values("normalized_name")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by("normalized_name")
        .values_list("normalized_name", flat=True)
    )
    for normalized_name in duplicate_names:
        tags = tuple(
            Tag.objects.filter(normalized_name=normalized_name).order_by(
                "created_at", "id"
            )
        )
        canonical = tags[0]
        effective = max(
            tags,
            key=lambda item: (
                _STATE_PRIORITY.get(item.state, 0),
                item.updated_at,
                str(item.id),
            ),
        )
        tag_ids = tuple(item.id for item in tags)
        duplicate_ids = tuple(item.id for item in tags[1:])

        _merge_revision_tags(
            RevisionTag,
            canonical_id=canonical.id,
            duplicate_ids=duplicate_ids,
        )
        _merge_article_tags(
            ArticleTag,
            canonical_id=canonical.id,
            duplicate_ids=duplicate_ids,
        )
        _merge_association_history(
            History,
            tag_ids=tag_ids,
            canonical_id=canonical.id,
        )
        _merge_restore_conflicts(
            Conflict,
            tag_ids=tag_ids,
            canonical_id=canonical.id,
        )

        duplicate_targets = [str(identity) for identity in duplicate_ids]
        AuditEntry.objects.filter(
            target_type="tag",
            target_id__in=duplicate_targets,
        ).update(target_id=str(canonical.id))
        Notification.objects.filter(
            target_type="tag",
            target_id__in=duplicate_targets,
        ).update(target_id=str(canonical.id))

        Tag.objects.filter(pk__in=duplicate_ids).delete()
        canonical.name = effective.name
        canonical.state = effective.state
        canonical.proposed_by_id = effective.proposed_by_id
        canonical.reviewed_by_id = effective.reviewed_by_id
        canonical.reviewed_at = effective.reviewed_at
        if canonical.state == "PENDING":
            canonical.reviewed_by_id = None
            canonical.reviewed_at = None
        canonical.save(
            update_fields=(
                "name",
                "state",
                "proposed_by",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            )
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("content", "0014_allow_rejected_tag_name_reproposal"),
        ("notifications", "0001_notification_foundation"),
        ("operations", "0002_audit_entry"),
    ]

    operations = [
        migrations.RunPython(
            merge_duplicate_tag_identities,
            reverse_code=migrations.RunPython.noop,
            atomic=True,
        ),
        migrations.RemoveConstraint(
            model_name="tag",
            name="content_tag_live_name_unique",
        ),
        migrations.AddConstraint(
            model_name="tag",
            constraint=models.UniqueConstraint(
                fields=("normalized_name",),
                name="content_tag_name_unique",
            ),
        ),
    ]
