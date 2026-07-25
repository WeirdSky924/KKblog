from django.db import models

from apps.core.ids import new_ulid


class ArticleModerationCase(models.Model):
    class Action(models.TextChoices):
        HIDE = "HIDE", "隐藏"
        DELETE = "DELETE", "删除"

    class State(models.TextChoices):
        ACTIVE = "ACTIVE", "生效中"
        RESTORED = "RESTORED", "已主动恢复"
        APPEALED = "APPEALED", "申诉待复审"
        FINAL_UPHELD = "FINAL_UPHELD", "终局维持"
        FINAL_REJECTED = "FINAL_REJECTED", "终局撤销"
        CLOSED = "CLOSED", "已关闭"

    class ClosureReason(models.TextChoices):
        ACCOUNT_DELETED = "ACCOUNT_DELETED", "作者账户已删除"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    article_id = models.CharField(max_length=26, editable=False)
    author_id = models.UUIDField(editable=False)
    action = models.CharField(max_length=12, choices=Action.choices, editable=False)
    state = models.CharField(
        max_length=24,
        choices=State.choices,
        default=State.ACTIVE,
    )
    pre_action_snapshot = models.JSONField(editable=False)
    reason = models.CharField(max_length=200, blank=True, default="")
    acted_by_id = models.UUIDField(editable=False)
    acted_at = models.DateTimeField(editable=False)
    resolved_by_id = models.UUIDField(null=True, blank=True, editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)
    recovery_error_code = models.CharField(max_length=128, blank=True, default="")
    closure_reason = models.CharField(
        max_length=32,
        choices=ClosureReason.choices,
        blank=True,
        default="",
    )
    closure_deletion_id = models.CharField(max_length=26, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "moderation_article_case"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="moderation_article_case_id_shape",
            ),
            models.CheckConstraint(
                condition=models.Q(article_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="moderation_article_case_target_shape",
            ),
            models.UniqueConstraint(
                fields=("article_id",),
                condition=(
                    models.Q(state__in=("ACTIVE", "APPEALED", "FINAL_UPHELD"))
                    | (
                        models.Q(state="FINAL_REJECTED")
                        & ~models.Q(recovery_error_code="")
                    )
                ),
                name="moderation_article_case_effect_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state__in=("ACTIVE", "APPEALED"),
                        resolved_by_id__isnull=True,
                        resolved_at__isnull=True,
                        recovery_error_code="",
                        closure_reason="",
                        closure_deletion_id="",
                    )
                    | models.Q(
                        state__in=(
                            "RESTORED",
                            "FINAL_UPHELD",
                            "FINAL_REJECTED",
                        ),
                        resolved_by_id__isnull=False,
                        resolved_at__isnull=False,
                        closure_reason="",
                        closure_deletion_id="",
                    )
                    | models.Q(
                        state="CLOSED",
                        resolved_by_id__isnull=False,
                        resolved_at__isnull=False,
                        recovery_error_code="",
                        closure_reason="ACCOUNT_DELETED",
                        closure_deletion_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$",
                    )
                ),
                name="moderation_article_case_resolution_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(recovery_error_code="") | models.Q(state="FINAL_REJECTED")
                ),
                name="moderation_article_case_recovery_error",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "created_at", "id"),
                name="mod_article_case_queue_idx",
            ),
            models.Index(
                fields=("author_id", "created_at"),
                name="mod_article_case_author_idx",
            ),
        ]
