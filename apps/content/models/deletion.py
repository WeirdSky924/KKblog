from django.db import models


class ArticleTombstone(models.Model):
    article_id = models.CharField(primary_key=True, max_length=26, editable=False)
    author_id = models.UUIDField(editable=False)
    deletion_actor_id = models.UUIDField(editable=False)
    administrative = models.BooleanField(editable=False)
    original_publication_state = models.CharField(max_length=16, editable=False)
    original_working_revision_id = models.CharField(
        max_length=26,
        null=True,
        editable=False,
    )
    original_published_revision_id = models.CharField(
        max_length=26,
        null=True,
        editable=False,
    )
    original_scheduled_revision_id = models.CharField(
        max_length=26,
        null=True,
        editable=False,
    )
    original_scheduled_for = models.DateTimeField(null=True, editable=False)
    original_scheduled_at = models.DateTimeField(null=True, editable=False)
    original_published_at = models.DateTimeField(null=True, editable=False)
    original_last_published_at = models.DateTimeField(null=True, editable=False)
    deleted_at = models.DateTimeField(editable=False)
    purge_after = models.DateTimeField(editable=False)
    purged_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "content_article_tombstone"
        indexes = [
            models.Index(
                fields=("purged_at", "purge_after"),
                name="content_tombstone_purge_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    original_publication_state__in=(
                        "DRAFT",
                        "SCHEDULED",
                        "PUBLISHED",
                    )
                ),
                name="content_tombstone_publication_state",
            ),
            models.CheckConstraint(
                condition=models.Q(purge_after__gt=models.F("deleted_at")),
                name="content_tombstone_deadline_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(purged_at__isnull=True)
                    | models.Q(purged_at__gte=models.F("purge_after"))
                ),
                name="content_tombstone_purged_at_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        original_publication_state="SCHEDULED",
                        original_scheduled_revision_id__isnull=False,
                        original_scheduled_for__isnull=False,
                        original_scheduled_at__isnull=False,
                    )
                    | (
                        ~models.Q(original_publication_state="SCHEDULED")
                        & models.Q(
                            original_scheduled_revision_id__isnull=True,
                            original_scheduled_for__isnull=True,
                            original_scheduled_at__isnull=True,
                        )
                    )
                ),
                name="content_tombstone_schedule_shape",
            ),
        ]
