from django.db import models
from django.db.models import F, Q

from apps.agents.contracts import (
    DEFAULT_CONCURRENCY_LIMIT,
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_PER_RUN_TOKEN_LIMIT,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_SITE_DAILY_TOKEN_LIMIT,
    MAX_CONCURRENCY_LIMIT,
    MAX_CONTEXT_WINDOW_TOKENS,
    MAX_ENDPOINT_DAILY_TOKEN_LIMIT,
    MAX_MAX_OUTPUT_TOKENS,
    MAX_PER_RUN_TOKEN_LIMIT,
    MAX_REQUEST_TIMEOUT_SECONDS,
    MAX_SITE_DAILY_TOKEN_LIMIT,
    MIN_CONCURRENCY_LIMIT,
    MIN_CONTEXT_WINDOW_TOKENS,
    MIN_ENDPOINT_DAILY_TOKEN_LIMIT,
    MIN_MAX_OUTPUT_TOKENS,
    MIN_PER_RUN_TOKEN_LIMIT,
    MIN_REQUEST_TIMEOUT_SECONDS,
    MIN_SITE_DAILY_TOKEN_LIMIT,
    MIN_THINKING_BUDGET_TOKENS,
    REASONING_EFFORT_VALUES,
)
from apps.core.ids import new_uuid


class AgentSitePolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    daily_token_limit = models.PositiveBigIntegerField(
        default=DEFAULT_SITE_DAILY_TOKEN_LIMIT
    )
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_site_policy"
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="agent_site_singleton"),
            models.CheckConstraint(
                condition=Q(
                    daily_token_limit__gte=MIN_SITE_DAILY_TOKEN_LIMIT,
                    daily_token_limit__lte=MAX_SITE_DAILY_TOKEN_LIMIT,
                ),
                name="agent_site_daily_limit_range",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="agent_site_version_positive",
            ),
        ]


class AgentEndpoint(models.Model):
    class Protocol(models.TextChoices):
        OPENAI_GPT = "OPENAI_GPT", "GPT / OpenAI compatible"
        OPENAI_DEEPSEEK = "OPENAI_DEEPSEEK", "DeepSeek compatible"
        ANTHROPIC = "ANTHROPIC", "Claude / Anthropic Messages"

    class AuthenticationMode(models.TextChoices):
        NONE = "NONE", "No authentication"
        SECRET_ALIAS = "SECRET_ALIAS", "Server secret alias"
        CUSTOM_API_KEY = "CUSTOM_API_KEY", "Custom API key"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    display_name = models.CharField(max_length=80, unique=True)
    protocol = models.CharField(max_length=24, choices=Protocol.choices)
    base_url = models.CharField(max_length=500)
    model_name = models.CharField(max_length=160)
    authentication_mode = models.CharField(
        max_length=24,
        choices=AuthenticationMode.choices,
        default=AuthenticationMode.NONE,
    )
    secret_alias = models.CharField(max_length=64, blank=True, default="")
    api_key_ciphertext = models.TextField(blank=True, default="", editable=False)
    enabled = models.BooleanField(default=False)
    context_window_tokens = models.PositiveIntegerField(
        default=DEFAULT_CONTEXT_WINDOW_TOKENS
    )
    max_output_tokens = models.PositiveIntegerField(default=DEFAULT_MAX_OUTPUT_TOKENS)
    reasoning_effort = models.CharField(max_length=8, blank=True, default="")
    thinking_budget_tokens = models.PositiveIntegerField(null=True, blank=True)
    per_run_token_limit = models.PositiveIntegerField(
        default=DEFAULT_PER_RUN_TOKEN_LIMIT
    )
    request_timeout_seconds = models.PositiveSmallIntegerField(
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS
    )
    concurrency_limit = models.PositiveSmallIntegerField(
        default=DEFAULT_CONCURRENCY_LIMIT
    )
    daily_token_limit = models.PositiveBigIntegerField(
        default=DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT
    )
    input_price_per_million_tokens = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True
    )
    output_price_per_million_tokens = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True
    )
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_endpoint"
        ordering = ("display_name", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    protocol__in=("OPENAI_GPT", "OPENAI_DEEPSEEK", "ANTHROPIC")
                ),
                name="agent_endpoint_protocol_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    authentication_mode__in=("NONE", "SECRET_ALIAS", "CUSTOM_API_KEY")
                ),
                name="agent_endpoint_auth_mode_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        authentication_mode="NONE",
                        secret_alias="",
                        api_key_ciphertext="",
                    )
                    | (
                        Q(authentication_mode="SECRET_ALIAS")
                        & ~Q(secret_alias="")
                        & Q(api_key_ciphertext="")
                    )
                    | (
                        Q(authentication_mode="CUSTOM_API_KEY")
                        & Q(secret_alias="")
                        & ~Q(api_key_ciphertext="")
                    )
                ),
                name="agent_endpoint_auth_shape",
            ),
            models.CheckConstraint(
                condition=Q(
                    context_window_tokens__gte=MIN_CONTEXT_WINDOW_TOKENS,
                    context_window_tokens__lte=MAX_CONTEXT_WINDOW_TOKENS,
                ),
                name="agent_endpoint_context_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    max_output_tokens__gte=MIN_MAX_OUTPUT_TOKENS,
                    max_output_tokens__lte=MAX_MAX_OUTPUT_TOKENS,
                )
                & Q(max_output_tokens__lt=F("context_window_tokens")),
                name="agent_endpoint_output_range",
            ),
            models.CheckConstraint(
                condition=Q(reasoning_effort__in=REASONING_EFFORT_VALUES),
                name="agent_endpoint_reasoning_effort_valid",
            ),
            models.CheckConstraint(
                condition=Q(thinking_budget_tokens__isnull=True)
                | Q(
                    thinking_budget_tokens__gte=MIN_THINKING_BUDGET_TOKENS,
                    thinking_budget_tokens__lt=F("max_output_tokens"),
                ),
                name="agent_endpoint_thinking_budget_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    per_run_token_limit__gte=MIN_PER_RUN_TOKEN_LIMIT,
                    per_run_token_limit__lte=MAX_PER_RUN_TOKEN_LIMIT,
                )
                & Q(per_run_token_limit__gte=F("max_output_tokens"))
                & Q(per_run_token_limit__lte=F("daily_token_limit")),
                name="agent_endpoint_run_limit_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    request_timeout_seconds__gte=MIN_REQUEST_TIMEOUT_SECONDS,
                    request_timeout_seconds__lte=MAX_REQUEST_TIMEOUT_SECONDS,
                ),
                name="agent_endpoint_timeout_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    concurrency_limit__gte=MIN_CONCURRENCY_LIMIT,
                    concurrency_limit__lte=MAX_CONCURRENCY_LIMIT,
                ),
                name="agent_endpoint_concurrency_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    daily_token_limit__gte=MIN_ENDPOINT_DAILY_TOKEN_LIMIT,
                    daily_token_limit__lte=MAX_ENDPOINT_DAILY_TOKEN_LIMIT,
                ),
                name="agent_endpoint_daily_range",
            ),
            models.CheckConstraint(
                condition=Q(input_price_per_million_tokens__isnull=True)
                | Q(input_price_per_million_tokens__gte=0),
                name="agent_endpoint_input_price_valid",
            ),
            models.CheckConstraint(
                condition=Q(output_price_per_million_tokens__isnull=True)
                | Q(output_price_per_million_tokens__gte=0),
                name="agent_endpoint_output_price_valid",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="agent_endpoint_version_positive",
            ),
        ]


class AgentProfile(models.Model):
    class Purpose(models.TextChoices):
        KNOWLEDGE_REVIEW = "KNOWLEDGE_REVIEW", "Knowledge review"
        QUESTION_GENERATION = "QUESTION_GENERATION", "Question generation"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    key = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=80)
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    endpoint = models.ForeignKey(
        AgentEndpoint, related_name="profiles", on_delete=models.PROTECT
    )
    schema_key = models.CharField(max_length=96)
    current_prompt = models.ForeignKey(
        "agents.AgentPromptRevision",
        related_name="current_for_profiles",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    enabled = models.BooleanField(default=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "agent_profile"
        ordering = ("display_name", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(purpose__in=("KNOWLEDGE_REVIEW", "QUESTION_GENERATION")),
                name="agent_profile_purpose_valid",
            ),
            models.CheckConstraint(
                condition=Q(enabled=False) | Q(current_prompt__isnull=False),
                name="agent_profile_enabled_has_prompt",
            ),
            models.CheckConstraint(
                condition=Q(row_version__gte=1),
                name="agent_profile_version_positive",
            ),
        ]


class AgentPromptRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    profile = models.ForeignKey(
        AgentProfile, related_name="prompt_revisions", on_delete=models.PROTECT
    )
    sequence = models.PositiveIntegerField()
    markdown_source = models.TextField()
    content_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        "accounts.Account",
        related_name="agent_prompt_revisions",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "agent_prompt_revision"
        ordering = ("profile_id", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "sequence"),
                name="agent_prompt_profile_sequence_unique",
            ),
            models.CheckConstraint(
                condition=Q(sequence__gte=1),
                name="agent_prompt_sequence_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("AgentPromptRevision is immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AgentPromptRevision is immutable")
