from django.db import models

from apps.core.ids import new_ulid


class ArticleAppeal(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "待复审"
        FINAL_UPHELD = "FINAL_UPHELD", "终局维持"
        FINAL_REJECTED = "FINAL_REJECTED", "终局撤销"
        CLOSED = "CLOSED", "已关闭"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    case = models.OneToOneField(
        "moderation.ArticleModerationCase",
        related_name="appeal",
        on_delete=models.CASCADE,
    )
    appellant_id = models.UUIDField(editable=False)
    statement = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(
        max_length=24,
        choices=State.choices,
        default=State.PENDING,
    )
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=200, blank=True, default="")
    recovery_error_code = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "moderation_article_appeal"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="moderation_article_appeal_id_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state__in=("PENDING", "CLOSED"),
                        reviewed_by_id__isnull=True,
                        reviewed_at__isnull=True,
                        decision_reason="",
                        recovery_error_code="",
                    )
                    | models.Q(
                        state__in=("FINAL_UPHELD", "FINAL_REJECTED"),
                        reviewed_by_id__isnull=False,
                        reviewed_at__isnull=False,
                    )
                ),
                name="moderation_article_appeal_review_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(recovery_error_code="") | models.Q(state="FINAL_REJECTED")
                ),
                name="moderation_article_appeal_recovery_error",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "created_at", "id"),
                name="mod_article_appeal_queue_idx",
            )
        ]
