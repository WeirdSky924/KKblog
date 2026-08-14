from django.db import models
from django.db.models import F, Q

from apps.core.ids import new_ulid


class OpportunityCheckRun(models.Model):
    class Kind(models.TextChoices):
        FULL = "FULL", "全部来源"
        SOURCE = "SOURCE", "单个来源"

    class State(models.TextChoices):
        PENDING = "PENDING", "等待执行"
        RUNNING = "RUNNING", "运行中"
        CANCEL_REQUESTED = "CANCEL_REQUESTED", "等待安全取消"
        SUCCEEDED = "SUCCEEDED", "成功"
        PARTIAL = "PARTIAL", "部分成功"
        FAILED = "FAILED", "失败"
        TRUNCATED = "TRUNCATED", "结果截断"
        CANCELLED = "CANCELLED", "已取消"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    trigger = models.CharField(
        max_length=20,
        choices=(
            ("SCHEDULED", "定时"),
            ("MANUAL_SOURCE", "手动单来源"),
            ("MANUAL_ALL", "手动全部"),
        ),
    )
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.PENDING,
        editable=False,
    )
    requested_by = models.ForeignKey(
        "accounts.Account",
        related_name="opportunity_check_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    current_source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
    )
    task_run_id = models.CharField(max_length=26, blank=True, editable=False)
    total_sources = models.PositiveIntegerField(default=0, editable=False)
    succeeded_sources = models.PositiveIntegerField(default=0, editable=False)
    failed_sources = models.PositiveIntegerField(default=0, editable=False)
    truncated_sources = models.PositiveIntegerField(default=0, editable=False)
    skipped_sources = models.PositiveIntegerField(default=0, editable=False)
    not_executed_sources = models.PositiveIntegerField(default=0, editable=False)
    created_opportunities = models.PositiveIntegerField(default=0, editable=False)
    changed_opportunities = models.PositiveIntegerField(default=0, editable=False)
    missing_opportunities = models.PositiveIntegerField(default=0, editable=False)
    failed_opportunity_checks = models.PositiveIntegerField(default=0, editable=False)
    cancel_requested_at = models.DateTimeField(null=True, blank=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity_check_run"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=("FULL", "SOURCE")),
                name="opp_check_run_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(trigger__in=("SCHEDULED", "MANUAL_SOURCE", "MANUAL_ALL")),
                name="opp_check_run_trigger_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    state__in=(
                        "PENDING",
                        "RUNNING",
                        "CANCEL_REQUESTED",
                        "SUCCEEDED",
                        "PARTIAL",
                        "FAILED",
                        "TRUNCATED",
                        "CANCELLED",
                    )
                ),
                name="opp_check_run_state_valid",
            ),
            models.UniqueConstraint(
                models.Value(1),
                condition=Q(state__in=("PENDING", "RUNNING", "CANCEL_REQUESTED")),
                name="opp_check_run_one_active",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state__in=("PENDING", "RUNNING", "CANCEL_REQUESTED"),
                        completed_at__isnull=True,
                    )
                    | Q(
                        state__in=(
                            "SUCCEEDED",
                            "PARTIAL",
                            "FAILED",
                            "TRUNCATED",
                            "CANCELLED",
                        ),
                        completed_at__isnull=False,
                    )
                ),
                name="opp_check_run_completion_shape",
            ),
        ]
        indexes = [
            models.Index(fields=("state", "-created_at"), name="opp_run_state_idx")
        ]


class OpportunityCheckRunSource(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "等待执行"
        RUNNING = "RUNNING", "运行中"
        SUCCEEDED = "SUCCEEDED", "成功"
        FAILED = "FAILED", "失败"
        TRUNCATED = "TRUNCATED", "结果截断"
        SKIPPED = "SKIPPED", "跳过"
        NOT_EXECUTED = "NOT_EXECUTED", "未执行"

    id = models.BigAutoField(primary_key=True)
    run = models.ForeignKey(
        OpportunityCheckRun,
        related_name="source_runs",
        on_delete=models.CASCADE,
    )
    source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="check_run_items",
        on_delete=models.PROTECT,
    )
    position = models.PositiveIntegerField()
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.PENDING,
        editable=False,
    )
    source_check = models.ForeignKey(
        "opportunities.OpportunityCheck",
        related_name="run_source_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    opportunity_checks = models.PositiveIntegerField(default=0, editable=False)
    created_opportunities = models.PositiveIntegerField(default=0, editable=False)
    changed_opportunities = models.PositiveIntegerField(default=0, editable=False)
    missing_opportunities = models.PositiveIntegerField(default=0, editable=False)
    failed_opportunity_checks = models.PositiveIntegerField(default=0, editable=False)
    safe_error_code = models.CharField(max_length=96, blank=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "opportunity_check_run_source"
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("run", "source"), name="opp_run_source_unique"
            ),
            models.UniqueConstraint(
                fields=("run", "position"), name="opp_run_position_unique"
            ),
            models.CheckConstraint(
                condition=Q(position__gte=1), name="opp_run_position_positive"
            ),
            models.CheckConstraint(
                condition=Q(
                    state__in=(
                        "PENDING",
                        "RUNNING",
                        "SUCCEEDED",
                        "FAILED",
                        "TRUNCATED",
                        "SKIPPED",
                        "NOT_EXECUTED",
                    )
                ),
                name="opp_run_source_state_valid",
            ),
        ]


class OpportunityCollectionSnapshot(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="collection_snapshots",
        on_delete=models.PROTECT,
    )
    source_check = models.OneToOneField(
        "opportunities.OpportunityCheck",
        related_name="collection_snapshot",
        on_delete=models.PROTECT,
    )
    complete = models.BooleanField(editable=False)
    truncated = models.BooleanField(editable=False)
    opportunity_identity_hashes = models.JSONField(default=list, editable=False)
    opportunity_field_hashes = models.JSONField(default=dict, editable=False)
    category_labels = models.JSONField(default=list, editable=False)
    city_labels = models.JSONField(default=list, editable=False)
    cohort_labels = models.JSONField(default=list, editable=False)
    difference_summary = models.JSONField(default=dict, editable=False)
    observed_at = models.DateTimeField(editable=False)
    expires_at = models.DateTimeField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_collection_snapshot"
        ordering = ("-observed_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=~Q(complete=True, truncated=True),
                name="opp_snapshot_completion_shape",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("observed_at")),
                name="opp_snapshot_expiry_after_observed",
            ),
        ]
        indexes = [
            models.Index(fields=("expires_at", "id"), name="opp_snapshot_expiry_idx")
        ]


class OpportunityStateTransition(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        related_name="state_transitions",
        on_delete=models.PROTECT,
    )
    source_check = models.ForeignKey(
        "opportunities.OpportunityCheck",
        related_name="state_transitions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    previous_status = models.CharField(max_length=16, editable=False)
    current_status = models.CharField(max_length=16, editable=False)
    reason_code = models.CharField(max_length=96, editable=False)
    occurred_at = models.DateTimeField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_state_transition"
        ordering = ("-occurred_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    previous_status__in=("CONFIRMED", "PENDING", "EXPIRED"),
                    current_status__in=("CONFIRMED", "PENDING", "EXPIRED"),
                ),
                name="opp_transition_status_valid",
            ),
            models.CheckConstraint(
                condition=~Q(previous_status=F("current_status")),
                name="opp_transition_status_changed",
            ),
        ]
        indexes = [
            models.Index(
                fields=("opportunity", "-occurred_at"),
                name="opp_transition_history_idx",
            )
        ]


class OpportunityCheck(models.Model):
    class TargetKind(models.TextChoices):
        SOURCE = "SOURCE", "来源列表"
        OPPORTUNITY = "OPPORTUNITY", "岗位链接"
        FILTERS = "FILTERS", "筛选选项"

    class Trigger(models.TextChoices):
        SCHEDULED = "SCHEDULED", "定时"
        MANUAL_SOURCE = "MANUAL_SOURCE", "手动单来源"
        MANUAL_ALL = "MANUAL_ALL", "手动全部"

    class State(models.TextChoices):
        RUNNING = "RUNNING", "运行中"
        SUCCEEDED = "SUCCEEDED", "成功"
        FAILED = "FAILED", "失败"
        TRUNCATED = "TRUNCATED", "结果截断"
        CANCELLED = "CANCELLED", "已取消"
        SKIPPED = "SKIPPED", "未执行"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="checks",
        on_delete=models.PROTECT,
    )
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        related_name="checks",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    task_run_id = models.CharField(max_length=26, blank=True, editable=False)
    target_kind = models.CharField(max_length=16, choices=TargetKind.choices)
    trigger = models.CharField(max_length=20, choices=Trigger.choices)
    state = models.CharField(max_length=16, choices=State.choices)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    final_url = models.URLField(max_length=2048, blank=True)
    page_title = models.CharField(max_length=300, blank=True)
    safe_error_code = models.CharField(max_length=96, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_check"
        ordering = ("-started_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(target_kind__in=("SOURCE", "OPPORTUNITY", "FILTERS")),
                name="opp_check_target_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(trigger__in=("SCHEDULED", "MANUAL_SOURCE", "MANUAL_ALL")),
                name="opp_check_trigger_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    state__in=(
                        "RUNNING",
                        "SUCCEEDED",
                        "FAILED",
                        "TRUNCATED",
                        "CANCELLED",
                        "SKIPPED",
                    )
                ),
                name="opp_check_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(target_kind="OPPORTUNITY", opportunity__isnull=False)
                    | Q(
                        target_kind__in=("SOURCE", "FILTERS"),
                        opportunity__isnull=True,
                    )
                ),
                name="opp_check_target_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="RUNNING", completed_at__isnull=True)
                    | Q(
                        state__in=(
                            "SUCCEEDED",
                            "FAILED",
                            "TRUNCATED",
                            "CANCELLED",
                            "SKIPPED",
                        ),
                        completed_at__isnull=False,
                    )
                ),
                name="opp_check_completion_shape",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("started_at")),
                name="opp_check_expiry_after_start",
            ),
            models.CheckConstraint(
                condition=Q(http_status__isnull=True)
                | Q(http_status__gte=100, http_status__lte=599),
                name="opp_check_http_status_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=("source", "target_kind", "-started_at"),
                name="opp_check_source_history_idx",
            ),
            models.Index(
                fields=("opportunity", "-started_at"),
                name="opp_check_job_history_idx",
            ),
            models.Index(fields=("expires_at", "id"), name="opp_check_expiry_idx"),
        ]


class OpportunityReviewItem(models.Model):
    class Kind(models.TextChoices):
        NEW = "NEW", "新岗位"
        FIELD_CHANGE = "FIELD_CHANGE", "字段变化"
        LIST_MISSING = "LIST_MISSING", "来源列表缺失"

    class State(models.TextChoices):
        OPEN = "OPEN", "待处理"
        ACCEPTED = "ACCEPTED", "已接受"
        KEPT_MANUAL = "KEPT_MANUAL", "保留人工值"
        RESOLVED = "RESOLVED", "已处理"

    id = models.CharField(
        primary_key=True,
        max_length=26,
        default=new_ulid,
        editable=False,
    )
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        related_name="review_items",
        on_delete=models.PROTECT,
    )
    source_check = models.ForeignKey(
        OpportunityCheck,
        related_name="review_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)
    field_changes = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.Account",
        related_name="opportunity_reviews",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity_review_item"
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=("NEW", "FIELD_CHANGE", "LIST_MISSING")),
                name="opp_review_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(state__in=("OPEN", "ACCEPTED", "KEPT_MANUAL", "RESOLVED")),
                name="opp_review_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="OPEN", reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | Q(
                        state__in=("ACCEPTED", "KEPT_MANUAL", "RESOLVED"),
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                    )
                ),
                name="opp_review_resolution_shape",
            ),
            models.UniqueConstraint(
                fields=("opportunity", "kind"),
                condition=Q(state="OPEN"),
                name="opp_review_open_kind_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "kind", "created_at"),
                name="opp_review_queue_idx",
            )
        ]
