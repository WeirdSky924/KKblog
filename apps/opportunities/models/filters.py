from django.db import models

from apps.core.ids import new_uuid


class OpportunityFilterKind(models.TextChoices):
    CITY = "CITY", "城市"
    CATEGORY = "CATEGORY", "岗位类别"
    COHORT = "COHORT", "届别"


class OpportunityFilterOption(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    kind = models.CharField(max_length=16, choices=OpportunityFilterKind.choices)
    label = models.CharField(max_length=100)
    normalized_label = models.CharField(max_length=100, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity_filter_option"
        ordering = ("kind", "normalized_label", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=OpportunityFilterKind.values),
                name="opp_filter_kind_valid",
            ),
            models.UniqueConstraint(
                fields=("kind", "normalized_label"),
                name="opp_filter_kind_name_unique",
            ),
        ]


class OpportunitySourceFilterOption(models.Model):
    source = models.ForeignKey(
        "opportunities.OpportunitySource",
        related_name="filter_observations",
        on_delete=models.CASCADE,
    )
    option = models.ForeignKey(
        OpportunityFilterOption,
        related_name="source_observations",
        on_delete=models.PROTECT,
    )
    active = models.BooleanField(default=True, editable=False)
    first_observed_at = models.DateTimeField(editable=False)
    last_observed_at = models.DateTimeField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "opportunity_source_filter_option"
        ordering = ("option__kind", "option__normalized_label", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "option"),
                name="opp_source_filter_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(last_observed_at__gte=models.F("first_observed_at")),
                name="opp_source_filter_observed_order",
            ),
        ]
        indexes = [
            models.Index(
                fields=("active", "option", "source"),
                name="opp_source_filter_active_idx",
            )
        ]
