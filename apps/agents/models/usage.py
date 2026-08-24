from django.db import models
from django.db.models import F, Q

from apps.core.ids import new_ulid


class AgentTokenLedger(models.Model):
    class Scope(models.TextChoices):
        SITE = "SITE", "Site"
        ENDPOINT = "ENDPOINT", "Endpoint"

    scope = models.CharField(max_length=12, choices=Scope.choices)
    endpoint = models.ForeignKey(
        "agents.AgentEndpoint",
        related_name="token_ledgers",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    usage_date = models.DateField()
    settled_tokens = models.PositiveBigIntegerField(default=0)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_token_ledger"
        ordering = ("-usage_date", "scope", "endpoint_id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope="SITE", endpoint__isnull=True)
                    | Q(scope="ENDPOINT", endpoint__isnull=False)
                ),
                name="agent_token_ledger_scope_shape",
            ),
            models.UniqueConstraint(
                fields=("usage_date",),
                condition=Q(scope="SITE"),
                name="agent_token_site_date_unique",
            ),
            models.UniqueConstraint(
                fields=("endpoint", "usage_date"),
                condition=Q(scope="ENDPOINT"),
                name="agent_token_endpoint_date_unique",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="agent_token_ledger_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("usage_date", "scope"), name="agent_token_ledger_date_idx"
            )
        ]


class AgentTokenReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SETTLED = "SETTLED", "Settled"
        RELEASED = "RELEASED", "Released"
        EXPIRED = "EXPIRED", "Expired"

    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    invocation = models.OneToOneField(
        "agents.AgentInvocation",
        related_name="token_reservation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    endpoint_check = models.OneToOneField(
        "agents.AgentEndpointCheck",
        related_name="token_reservation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    site_ledger = models.ForeignKey(
        AgentTokenLedger, related_name="site_reservations", on_delete=models.PROTECT
    )
    endpoint_ledger = models.ForeignKey(
        AgentTokenLedger,
        related_name="endpoint_reservations",
        on_delete=models.PROTECT,
    )
    idempotency_key = models.CharField(max_length=128, unique=True)
    requested_tokens = models.PositiveIntegerField()
    settled_tokens = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    lease_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_token_reservation"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_tokens__gte=1),
                name="agent_token_reservation_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(invocation__isnull=False, endpoint_check__isnull=True)
                    | Q(invocation__isnull=True, endpoint_check__isnull=False)
                ),
                name="agent_token_reservation_owner_shape",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("ACTIVE", "SETTLED", "RELEASED", "EXPIRED")),
                name="agent_token_reservation_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="ACTIVE", settled_tokens__isnull=True)
                    | Q(
                        status__in=("SETTLED", "EXPIRED"),
                        settled_tokens__isnull=False,
                        settled_tokens__lte=F("requested_tokens"),
                    )
                    | Q(status="RELEASED", settled_tokens=0)
                ),
                name="agent_token_reservation_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "lease_expires_at"),
                name="agent_token_reserve_lease_idx",
            )
        ]


class AgentTokenAdjustment(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    ledger = models.ForeignKey(
        AgentTokenLedger, related_name="adjustments", on_delete=models.PROTECT
    )
    actor_id = models.UUIDField(editable=False)
    idempotency_key = models.CharField(max_length=160, unique=True)
    amount = models.BigIntegerField()
    before_effective_tokens = models.PositiveBigIntegerField()
    after_effective_tokens = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "agent_token_adjustment"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount=0), name="agent_token_adjustment_nonzero"
            ),
            models.CheckConstraint(
                condition=Q(
                    after_effective_tokens=F("before_effective_tokens") + F("amount")
                ),
                name="agent_token_adjustment_balances",
            ),
        ]


class AgentTokenResetOperation(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    actor_id = models.UUIDField(editable=False)
    scope = models.CharField(max_length=12, choices=AgentTokenLedger.Scope.choices)
    endpoint = models.ForeignKey(
        "agents.AgentEndpoint",
        related_name="token_reset_operations",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    usage_date = models.DateField()
    idempotency_key = models.CharField(max_length=128, unique=True)
    reason = models.CharField(max_length=255)
    before_effective_tokens = models.PositiveBigIntegerField()
    after_effective_tokens = models.PositiveBigIntegerField(default=0)
    active_reservation_count = models.PositiveIntegerField(default=0)
    adjustment_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "agent_token_reset_operation"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope="SITE", endpoint__isnull=True)
                    | Q(
                        scope="ENDPOINT",
                        endpoint__isnull=False,
                    )
                ),
                name="agent_token_reset_scope_shape",
            ),
            models.CheckConstraint(
                condition=Q(after_effective_tokens=0),
                name="agent_token_reset_after_zero",
            ),
        ]
