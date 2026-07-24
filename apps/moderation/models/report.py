from django.db import models

from apps.core.ids import new_ulid


class ReportReason(models.TextChoices):
    SPAM = "SPAM", "垃圾广告"
    HARASSMENT = "HARASSMENT", "辱骂骚扰"
    ILLEGAL_DANGEROUS = "ILLEGAL_DANGEROUS", "违法危险"
    PRIVACY = "PRIVACY", "隐私泄露"
    IRRELEVANT = "IRRELEVANT", "无关内容"
    OTHER = "OTHER", "其他"


class Report(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "待初审"
        UPHELD = "UPHELD", "初审成立"
        REJECTED = "REJECTED", "初审驳回"
        APPEAL_PENDING = "APPEAL_PENDING", "申诉待复审"
        FINAL_UPHELD = "FINAL_UPHELD", "终局成立"
        FINAL_REJECTED = "FINAL_REJECTED", "终局驳回"
        CLOSED = "CLOSED", "已关闭"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    target_comment_id = models.CharField(max_length=26)
    reporter_id = models.UUIDField()
    reported_author_id = models.UUIDField(null=True, blank=True)
    reason = models.CharField(max_length=24, choices=ReportReason.choices)
    description = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(
        max_length=24,
        choices=State.choices,
        default=State.PENDING,
    )
    reviewed_by_id = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "moderation_report"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"),
                name="moderation_report_id_shape",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    target_comment_id__regex=r"^[0-9A-HJKMNP-TV-Z]{26}$"
                ),
                name="moderation_report_target_shape",
            ),
            models.UniqueConstraint(
                fields=("reporter_id", "target_comment_id"),
                name="moderation_report_reporter_target_unique",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(state="PENDING")
                    | models.Q(
                        reviewed_by_id__isnull=True,
                        reviewed_at__isnull=True,
                        decision_reason="",
                    )
                ),
                name="moderation_report_pending_review_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "created_at", "id"),
                name="moderation_report_queue_idx",
            ),
            models.Index(
                fields=("target_comment_id",),
                name="moderation_report_target_idx",
            ),
        ]
