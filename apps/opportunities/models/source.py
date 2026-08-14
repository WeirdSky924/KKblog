from django.db import models

from apps.core.ids import new_uuid


class OpportunitySource(models.Model):
    class SourceType(models.TextChoices):
        CAMPUS = "CAMPUS", "校园招聘"
        INTERNSHIP = "INTERNSHIP", "实习招聘"
        SOCIAL = "SOCIAL", "社会招聘"
        COMPREHENSIVE = "COMPREHENSIVE", "官方综合招聘"
        OTHER = "OTHER", "其他"

    class CheckState(models.TextChoices):
        NEVER = "NEVER", "尚未检查"
        HEALTHY = "HEALTHY", "正常"
        DEGRADED = "DEGRADED", "暂时异常"
        STALE = "STALE", "信息过期"
        UNSUPPORTED = "UNSUPPORTED", "暂不支持自动采集"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    company_name = models.CharField(max_length=120)
    normalized_company_name = models.CharField(max_length=120, editable=False)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    official_url = models.URLField(max_length=2048)
    note = models.CharField(max_length=500, blank=True)
    adapter_key = models.CharField(max_length=80)
    adapter_config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=False)
    publicly_visible = models.BooleanField(default=False, editable=False)
    respect_robots_txt = models.BooleanField(default=True)
    request_interval_seconds = models.PositiveSmallIntegerField(default=2)
    max_pages = models.PositiveSmallIntegerField(default=50)
    max_opportunities = models.PositiveIntegerField(default=5000)
    max_duration_seconds = models.PositiveIntegerField(default=600)
    check_state = models.CharField(
        max_length=16,
        choices=CheckState.choices,
        default=CheckState.NEVER,
        editable=False,
    )
    consecutive_failures = models.PositiveSmallIntegerField(default=0, editable=False)
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error_code = models.CharField(max_length=96, blank=True, editable=False)
    filter_options_stale = models.BooleanField(default=False, editable=False)
    last_filter_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity_source"
        ordering = ("normalized_company_name", "source_type", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    source_type__in=(
                        "CAMPUS",
                        "INTERNSHIP",
                        "SOCIAL",
                        "COMPREHENSIVE",
                        "OTHER",
                    )
                ),
                name="opp_source_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    check_state__in=(
                        "NEVER",
                        "HEALTHY",
                        "DEGRADED",
                        "STALE",
                        "UNSUPPORTED",
                    )
                ),
                name="opp_source_check_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(request_interval_seconds__gte=2),
                name="opp_source_request_interval_min",
            ),
            models.CheckConstraint(
                condition=models.Q(max_pages__gte=1),
                name="opp_source_max_pages_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(max_opportunities__gte=1),
                name="opp_source_max_items_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(max_duration_seconds__gte=1),
                name="opp_source_max_duration_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="opp_source_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(enabled=True) | models.Q(publicly_visible=False),
                name="opp_source_public_requires_enabled",
            ),
            models.UniqueConstraint(
                fields=("official_url",),
                name="opp_source_official_url_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("enabled", "publicly_visible", "normalized_company_name"),
                name="opp_source_public_idx",
            ),
            models.Index(
                fields=("check_state", "last_checked_at"),
                name="opp_source_check_idx",
            ),
        ]


class OpportunitySourceHost(models.Model):
    source = models.ForeignKey(
        OpportunitySource,
        related_name="allowed_hosts",
        on_delete=models.CASCADE,
    )
    hostname = models.CharField(max_length=253)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_source_host"
        ordering = ("hostname", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "hostname"),
                name="opp_source_host_unique",
            )
        ]
