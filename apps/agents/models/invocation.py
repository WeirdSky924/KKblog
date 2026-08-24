from django.db import models
from django.db.models import Q

from apps.core.ids import new_ulid


class AgentInvocation(models.Model):
    class State(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        REFUSED = "REFUSED", "Refused"
        INCOMPLETE = "INCOMPLETE", "Incomplete"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    profile = models.ForeignKey(
        "agents.AgentProfile", related_name="invocations", on_delete=models.PROTECT
    )
    prompt_revision = models.ForeignKey(
        "agents.AgentPromptRevision",
        related_name="invocations",
        on_delete=models.PROTECT,
    )
    endpoint = models.ForeignKey(
        "agents.AgentEndpoint", related_name="invocations", on_delete=models.PROTECT
    )
    caller_type = models.CharField(max_length=64)
    caller_id = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=128)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    profile_key_snapshot = models.CharField(max_length=64)
    schema_key_snapshot = models.CharField(max_length=96)
    prompt_sequence_snapshot = models.PositiveIntegerField()
    prompt_sha256_snapshot = models.CharField(max_length=64)
    endpoint_row_version_snapshot = models.PositiveBigIntegerField()
    endpoint_protocol_snapshot = models.CharField(max_length=24)
    endpoint_base_url_snapshot = models.CharField(max_length=500)
    model_name_snapshot = models.CharField(max_length=160)
    authentication_mode_snapshot = models.CharField(max_length=24)
    secret_alias_snapshot = models.CharField(max_length=64, blank=True, default="")
    api_key_ciphertext_snapshot = models.TextField(
        blank=True, default="", editable=False
    )
    context_window_tokens_snapshot = models.PositiveIntegerField()
    max_output_tokens_snapshot = models.PositiveIntegerField()
    reasoning_effort_snapshot = models.CharField(max_length=8, blank=True, default="")
    thinking_budget_tokens_snapshot = models.PositiveIntegerField(null=True, blank=True)
    per_run_token_limit_snapshot = models.PositiveIntegerField()
    request_timeout_seconds_snapshot = models.PositiveSmallIntegerField()
    concurrency_limit_snapshot = models.PositiveSmallIntegerField()
    endpoint_daily_token_limit_snapshot = models.PositiveBigIntegerField()
    site_daily_token_limit_snapshot = models.PositiveBigIntegerField()
    estimated_input_tokens = models.PositiveIntegerField()
    input_sha256 = models.CharField(max_length=64, blank=True, default="")
    output_sha256 = models.CharField(max_length=64, blank=True, default="")
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    safe_error_code = models.CharField(max_length=96, blank=True, default="")
    task_run_id = models.CharField(max_length=26, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_invocation"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("caller_type", "caller_id", "idempotency_key"),
                name="agent_invocation_caller_idempotent",
            ),
            models.CheckConstraint(
                condition=Q(
                    state__in=(
                        "PENDING",
                        "RUNNING",
                        "SUCCEEDED",
                        "FAILED",
                        "REFUSED",
                        "INCOMPLETE",
                        "CANCELLED",
                    )
                ),
                name="agent_invocation_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(prompt_sequence_snapshot__gte=1),
                name="agent_invocation_prompt_seq_positive",
            ),
            models.CheckConstraint(
                condition=Q(endpoint_row_version_snapshot__gte=1),
                name="agent_invocation_endpoint_ver_positive",
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
                name="agent_invocation_auth_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state__in=("PENDING", "RUNNING"),
                        completed_at__isnull=True,
                    )
                    | Q(
                        state__in=(
                            "SUCCEEDED",
                            "FAILED",
                            "REFUSED",
                            "INCOMPLETE",
                            "CANCELLED",
                        ),
                        completed_at__isnull=False,
                    )
                ),
                name="agent_invocation_terminal_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "created_at"), name="agent_invocation_state_idx"
            ),
            models.Index(
                fields=("endpoint", "created_at"),
                name="agent_invocation_endpoint_idx",
            ),
        ]


class AgentInvocationAttempt(models.Model):
    class Phase(models.TextChoices):
        PREPARE = "PREPARE", "Prepare"
        PROVIDER_RETRY = "PROVIDER_RETRY", "Provider retry"
        EXTRACT_REPAIR = "EXTRACT_REPAIR", "Extract repair"
        SCHEMA_REPAIR = "SCHEMA_REPAIR", "Schema repair"
        SEMANTIC_REPAIR = "SEMANTIC_REPAIR", "Semantic repair"
        ACCEPTED = "ACCEPTED", "Accepted"
        FAILED = "FAILED", "Failed"
        REFUSED = "REFUSED", "Refused"
        INCOMPLETE = "INCOMPLETE", "Incomplete"

    id = models.BigAutoField(primary_key=True)
    invocation = models.ForeignKey(
        AgentInvocation, related_name="attempts", on_delete=models.CASCADE
    )
    sequence = models.PositiveSmallIntegerField()
    phase = models.CharField(max_length=24, choices=Phase.choices)
    strategy = models.CharField(max_length=24)
    schema_key = models.CharField(max_length=96)
    schema_sha256 = models.CharField(max_length=64)
    adapter_version = models.CharField(max_length=32, default="v1")
    finish_reason = models.CharField(max_length=32, blank=True, default="")
    safe_error_code = models.CharField(max_length=96, blank=True, default="")
    input_bytes = models.PositiveIntegerField(default=0)
    output_bytes = models.PositiveIntegerField(default=0)
    usage_trusted = models.BooleanField(default=False)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_invocation_attempt"
        ordering = ("invocation_id", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("invocation", "sequence"),
                name="agent_attempt_invocation_sequence_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gte=1),
                name="agent_attempt_sequence_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    phase__in=(
                        "PREPARE",
                        "PROVIDER_RETRY",
                        "EXTRACT_REPAIR",
                        "SCHEMA_REPAIR",
                        "SEMANTIC_REPAIR",
                        "ACCEPTED",
                        "FAILED",
                        "REFUSED",
                        "INCOMPLETE",
                    )
                ),
                name="agent_attempt_phase_valid",
            ),
        ]
