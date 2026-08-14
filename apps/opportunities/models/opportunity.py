from django.db import models

from apps.core.ids import new_uuid


class Opportunity(models.Model):
    class RecruitmentType(models.TextChoices):
        CAMPUS = "CAMPUS", "校园招聘"
        INTERNSHIP = "INTERNSHIP", "实习招聘"
        SOCIAL = "SOCIAL", "社会招聘"
        FRESH_GRADUATE = "FRESH_GRADUATE", "应届生招聘"
        OTHER = "OTHER", "其他"

    class VerificationStatus(models.TextChoices):
        CONFIRMED = "CONFIRMED", "已确认"
        PENDING = "PENDING", "待确认"
        EXPIRED = "EXPIRED", "已过期"

    class PublicationState(models.TextChoices):
        PUBLISHED = "PUBLISHED", "在架"
        WITHDRAWN = "WITHDRAWN", "已下架"

    class Origin(models.TextChoices):
        MANUAL = "MANUAL", "人工创建"
        CRAWLER = "CRAWLER", "爬虫创建"
        IMPORT = "IMPORT", "参考数据导入"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="opportunities",
        on_delete=models.PROTECT,
    )
    title = models.CharField(max_length=200)
    target_url = models.URLField(max_length=2048)
    normalized_target_url = models.CharField(max_length=2048, editable=False)
    normalized_identity_title = models.CharField(max_length=600, editable=False)
    identity_key = models.CharField(max_length=64, editable=False)
    recruitment_type = models.CharField(
        max_length=20,
        choices=RecruitmentType.choices,
    )
    plan = models.CharField(max_length=200)
    location_text = models.CharField(max_length=300)
    public_evidence = models.CharField(max_length=1200)
    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    publication_state = models.CharField(
        max_length=16,
        choices=PublicationState.choices,
        default=PublicationState.PUBLISHED,
    )
    origin = models.CharField(max_length=12, choices=Origin.choices)
    title_overridden = models.BooleanField(default=False, editable=False)
    target_url_overridden = models.BooleanField(default=False, editable=False)
    recruitment_type_overridden = models.BooleanField(default=False, editable=False)
    plan_overridden = models.BooleanField(default=False, editable=False)
    location_overridden = models.BooleanField(default=False, editable=False)
    public_evidence_overridden = models.BooleanField(default=False, editable=False)
    category_overridden = models.BooleanField(default=False, editable=False)
    city_overridden = models.BooleanField(default=False, editable=False)
    cohort_overridden = models.BooleanField(default=False, editable=False)
    list_missing = models.BooleanField(default=False, editable=False)
    list_missing_count = models.PositiveSmallIntegerField(default=0, editable=False)
    consecutive_failures = models.PositiveSmallIntegerField(default=0, editable=False)
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error_code = models.CharField(max_length=96, blank=True, editable=False)
    last_collected_at = models.DateTimeField(null=True, blank=True, editable=False)
    source_disabled_previous_state = models.CharField(
        max_length=16,
        choices=PublicationState.choices,
        null=True,
        blank=True,
        editable=False,
    )
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity"
        ordering = ("source__normalized_company_name", "title", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    recruitment_type__in=(
                        "CAMPUS",
                        "INTERNSHIP",
                        "SOCIAL",
                        "FRESH_GRADUATE",
                        "OTHER",
                    )
                ),
                name="opp_recruitment_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    verification_status__in=("CONFIRMED", "PENDING", "EXPIRED")
                ),
                name="opp_verification_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(publication_state__in=("PUBLISHED", "WITHDRAWN")),
                name="opp_publication_state_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(origin__in=("MANUAL", "CRAWLER", "IMPORT")),
                name="opp_origin_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="opp_version_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(list_missing=True, list_missing_count__gte=2)
                    | models.Q(list_missing=False)
                ),
                name="opp_list_missing_count_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        source_disabled_previous_state__isnull=True,
                    )
                    | models.Q(
                        publication_state="WITHDRAWN",
                        source_disabled_previous_state__in=("PUBLISHED", "WITHDRAWN"),
                    )
                ),
                name="opp_source_disabled_state_shape",
            ),
            models.UniqueConstraint(
                fields=("source", "identity_key"),
                name="opp_source_identity_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("publication_state", "verification_status", "source"),
                name="opp_public_list_idx",
            ),
            models.Index(
                fields=("source", "origin", "updated_at"),
                name="opp_admin_source_idx",
            ),
        ]


class OpportunityFilterAssignment(models.Model):
    class Origin(models.TextChoices):
        COLLECTED = "COLLECTED", "采集"
        MANUAL = "MANUAL", "人工覆盖"

    opportunity = models.ForeignKey(
        Opportunity,
        related_name="filter_assignments",
        on_delete=models.CASCADE,
    )
    option = models.ForeignKey(
        "opportunities.OpportunityFilterOption",
        related_name="opportunity_assignments",
        on_delete=models.PROTECT,
    )
    origin = models.CharField(max_length=12, choices=Origin.choices)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_filter_assignment"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(origin__in=("COLLECTED", "MANUAL")),
                name="opp_assignment_origin_valid",
            ),
            models.UniqueConstraint(
                fields=("opportunity", "option", "origin"),
                name="opp_filter_assignment_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("option", "opportunity"),
                name="opp_filter_assignment_idx",
            )
        ]
