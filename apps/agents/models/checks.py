from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.ids import new_ulid


class AgentEndpointCheck(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    endpoint = models.ForeignKey(
        "agents.AgentEndpoint",
        related_name="connection_checks",
        on_delete=models.PROTECT,
    )
    requested_by_id = models.UUIDField(editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True)
    state = models.CharField(
        max_length=12, choices=State.choices, default=State.PENDING
    )
    endpoint_row_version_snapshot = models.PositiveBigIntegerField()
    protocol_snapshot = models.CharField(max_length=24)
    base_url_snapshot = models.CharField(max_length=500)
    model_name_snapshot = models.CharField(max_length=160)
    reasoning_effort_snapshot = models.CharField(max_length=8, blank=True, default="")
    thinking_budget_tokens_snapshot = models.PositiveIntegerField(null=True, blank=True)
    schema_key_snapshot = models.CharField(max_length=96, blank=True, default="")
    capability_strategy = models.CharField(max_length=24, blank=True, default="")
    capability_adapter_version = models.CharField(max_length=32, blank=True, default="")
    capability_state = models.CharField(max_length=24, default="CONNECTIVITY_ONLY")
    authentication_mode_snapshot = models.CharField(max_length=24)
    secret_alias_snapshot = models.CharField(max_length=64, blank=True, default="")
    api_key_ciphertext_snapshot = models.TextField(
        blank=True, default="", editable=False
    )
    request_timeout_seconds_snapshot = models.PositiveSmallIntegerField()
    concurrency_limit_snapshot = models.PositiveSmallIntegerField()
    endpoint_daily_token_limit_snapshot = models.PositiveBigIntegerField()
    site_daily_token_limit_snapshot = models.PositiveBigIntegerField()
    token_budget = models.PositiveIntegerField(default=2_048)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    usage_uncertain = models.BooleanField(default=False)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    safe_error_code = models.CharField(max_length=96, blank=True, default="")
    task_run_id = models.CharField(max_length=26, blank=True, default="")
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_endpoint_check"
        ordering = ("-requested_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(state__in=("PENDING", "RUNNING", "SUCCEEDED", "FAILED")),
                name="agent_endpoint_check_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(endpoint_row_version_snapshot__gte=1),
                name="agent_endpoint_check_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(token_budget__gte=256, token_budget__lte=10_000),
                name="agent_endpoint_check_budget_range",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__lte=3),
                name="agent_endpoint_check_attempt_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        authentication_mode_snapshot="NONE",
                        secret_alias_snapshot="",
                        api_key_ciphertext_snapshot="",
                    )
                    | (
                        Q(authentication_mode_snapshot="SECRET_ALIAS")
                        & ~Q(secret_alias_snapshot="")
                        & Q(api_key_ciphertext_snapshot="")
                    )
                    | (
                        Q(authentication_mode_snapshot="CUSTOM_API_KEY")
                        & Q(secret_alias_snapshot="")
                        & ~Q(api_key_ciphertext_snapshot="")
                    )
                ),
                name="agent_endpoint_check_auth_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state="PENDING",
                        started_at__isnull=True,
                        completed_at__isnull=True,
                    )
                    | Q(
                        state="RUNNING",
                        started_at__isnull=False,
                        completed_at__isnull=True,
                    )
                    | Q(
                        state__in=("SUCCEEDED", "FAILED"),
                        started_at__isnull=False,
                        completed_at__isnull=False,
                    )
                ),
                name="agent_endpoint_check_lifecycle_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("endpoint", "requested_at"), name="agent_check_endpoint_idx"
            ),
            models.Index(fields=("state", "created_at"), name="agent_check_state_idx"),
        ]
