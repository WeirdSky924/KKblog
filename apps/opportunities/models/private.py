from django.db import models
from django.db.models import Q


class OpportunityBookmark(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        related_name="opportunity_bookmarks",
        on_delete=models.CASCADE,
    )
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        related_name="bookmarks",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_bookmark"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("account", "opportunity"),
                name="opp_bookmark_account_job_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("account", "-created_at", "opportunity"),
                name="opp_bookmark_account_idx",
            )
        ]


class OpportunitySettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    default_city = models.ForeignKey(
        "opportunities.OpportunityFilterOption",
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    default_cohort = models.ForeignKey(
        "opportunities.OpportunityFilterOption",
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity_settings"
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="opp_settings_singleton"),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="opp_settings_version_positive",
            ),
        ]


class OpportunityDefaultFilterSelection(models.Model):
    class Kind(models.TextChoices):
        CITY = "CITY", "城市"
        STATUS = "STATUS", "核实状态"
        COMPANY = "COMPANY", "企业"
        RECRUITMENT_TYPE = "RECRUITMENT_TYPE", "招聘类型"
        CATEGORY = "CATEGORY", "岗位类别"
        COHORT = "COHORT", "届别"

    settings = models.ForeignKey(
        OpportunitySettings,
        related_name="default_filter_selections",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    option = models.ForeignKey(
        "opportunities.OpportunityFilterOption",
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="+",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    value = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "opportunity_default_filter_selection"
        ordering = ("kind", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    kind__in=(
                        "CITY",
                        "STATUS",
                        "COMPANY",
                        "RECRUITMENT_TYPE",
                        "CATEGORY",
                        "COHORT",
                    )
                ),
                name="opp_default_filter_kind_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        kind__in=("CITY", "CATEGORY", "COHORT"),
                        option__isnull=False,
                        source__isnull=True,
                        value="",
                    )
                    | Q(
                        kind="COMPANY",
                        option__isnull=True,
                        source__isnull=False,
                        value="",
                    )
                    | (
                        Q(
                            kind__in=("STATUS", "RECRUITMENT_TYPE"),
                            option__isnull=True,
                            source__isnull=True,
                        )
                        & ~Q(value="")
                    )
                ),
                name="opp_default_filter_shape",
            ),
            models.UniqueConstraint(
                fields=("settings", "kind", "option"),
                condition=Q(option__isnull=False),
                name="opp_default_filter_option_unique",
            ),
            models.UniqueConstraint(
                fields=("settings", "kind", "source"),
                condition=Q(source__isnull=False),
                name="opp_default_filter_source_unique",
            ),
            models.UniqueConstraint(
                fields=("settings", "kind", "value"),
                condition=~Q(value=""),
                name="opp_default_filter_value_unique",
            ),
        ]
