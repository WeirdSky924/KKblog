from django.db import models


class DeletedAccountIdentity(models.Model):
    account_id = models.UUIDField(primary_key=True, editable=False)
    deletion_id = models.CharField(max_length=26, unique=True, editable=False)
    deleted_at = models.DateTimeField(editable=False)

    class Meta:
        db_table = "moderation_deleted_account_identity"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(deletion_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="moderation_deleted_identity_id_shape",
            )
        ]
