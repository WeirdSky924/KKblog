from django.db import models


class AuthorContentMask(models.Model):
    author_id = models.UUIDField(primary_key=True, editable=False)
    masked = models.BooleanField(editable=False)
    last_event_at = models.DateTimeField(editable=False)
    last_event_id = models.CharField(max_length=26, editable=False)
    last_event_type = models.CharField(max_length=32, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "content_author_mask"
        indexes = [
            models.Index(
                fields=("masked", "author_id"),
                name="content_author_mask_state_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    last_event_type__in=(
                        "account.disabled.v1",
                        "account.enabled.v1",
                    )
                ),
                name="content_author_mask_event_type",
            ),
            models.CheckConstraint(
                condition=models.Q(last_event_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="content_author_mask_event_id_shape",
            ),
        ]
