from django.db import IntegrityError, transaction

from apps.agents.contracts import AgentCommandError, EndpointRuntimeSettings
from apps.agents.models import (
    AgentEndpointCheck,
    AgentInvocation,
    AgentProfile,
    AgentSitePolicy,
)
from apps.core.ids import normalize_ulid

from .common import (
    validate_bounded_identifier,
    validate_caller_type,
    validate_idempotency_key,
    validate_profile_key,
)


def _existing_invocation(
    *, caller_type: str, caller_id: str, idempotency_key: str
) -> AgentInvocation | None:
    return AgentInvocation.objects.filter(
        caller_type=caller_type,
        caller_id=caller_id,
        idempotency_key=idempotency_key,
    ).first()


def create_agent_invocation(
    *,
    profile_key,
    caller_type,
    caller_id,
    idempotency_key,
    estimated_input_tokens,
    task_run_id=None,
) -> AgentInvocation:
    stable_profile_key = validate_profile_key(profile_key)
    stable_caller_type = validate_caller_type(caller_type)
    stable_caller_id = validate_bounded_identifier(caller_id)
    stable_idempotency_key = validate_idempotency_key(idempotency_key)
    if task_run_id is None or task_run_id == "":
        stable_task_run_id = ""
    else:
        try:
            stable_task_run_id = normalize_ulid(task_run_id)
        except (TypeError, ValueError):
            raise AgentCommandError(
                "agents.invocation_invalid.v1", "任务运行标识不合法。"
            ) from None
    existing = _existing_invocation(
        caller_type=stable_caller_type,
        caller_id=stable_caller_id,
        idempotency_key=stable_idempotency_key,
    )
    if existing is not None:
        if (
            existing.profile_key_snapshot != stable_profile_key
            or existing.estimated_input_tokens != estimated_input_tokens
            or existing.task_run_id != stable_task_run_id
        ):
            raise AgentCommandError(
                "agents.idempotency_conflict.v1",
                "相同幂等标识已用于不同调用。",
            )
        return existing

    with transaction.atomic():
        try:
            profile = AgentProfile.objects.select_related(
                "endpoint", "current_prompt"
            ).get(key=stable_profile_key, enabled=True)
        except AgentProfile.DoesNotExist:
            raise AgentCommandError(
                "agents.profile_unavailable.v1", "当前没有可用的 AGENT。"
            ) from None
        endpoint = profile.endpoint
        prompt = profile.current_prompt
        if not endpoint.enabled or prompt is None or prompt.profile_id != profile.id:
            raise AgentCommandError(
                "agents.profile_unavailable.v1", "当前没有可用的 AGENT。"
            )
        if not AgentEndpointCheck.objects.filter(
            endpoint=endpoint,
            endpoint_row_version_snapshot=endpoint.row_version,
            state=AgentEndpointCheck.State.SUCCEEDED,
            schema_key_snapshot=profile.schema_key,
            capability_state="SCHEMA_SUPPORTED",
        ).exists():
            raise AgentCommandError(
                "agents.profile_capability_unverified.v1",
                "当前 AGENT 的 Endpoint 能力检查已缺失或失效。",
            )
        policy, _ = AgentSitePolicy.objects.get_or_create(pk=1)
        runtime = EndpointRuntimeSettings(
            context_window_tokens=endpoint.context_window_tokens,
            max_output_tokens=endpoint.max_output_tokens,
            reasoning_effort=endpoint.reasoning_effort,
            thinking_budget_tokens=endpoint.thinking_budget_tokens,
            per_run_token_limit=endpoint.per_run_token_limit,
            request_timeout_seconds=endpoint.request_timeout_seconds,
            concurrency_limit=endpoint.concurrency_limit,
            endpoint_daily_token_limit=endpoint.daily_token_limit,
        ).validate(site_daily_token_limit=policy.daily_token_limit)
        estimate = runtime.validate_input_estimate(estimated_input_tokens)
        try:
            with transaction.atomic():
                invocation = AgentInvocation.objects.create(
                    profile=profile,
                    prompt_revision=prompt,
                    endpoint=endpoint,
                    caller_type=stable_caller_type,
                    caller_id=stable_caller_id,
                    idempotency_key=stable_idempotency_key,
                    profile_key_snapshot=profile.key,
                    schema_key_snapshot=profile.schema_key,
                    prompt_sequence_snapshot=prompt.sequence,
                    prompt_sha256_snapshot=prompt.content_sha256,
                    endpoint_row_version_snapshot=endpoint.row_version,
                    endpoint_protocol_snapshot=endpoint.protocol,
                    endpoint_base_url_snapshot=endpoint.base_url,
                    model_name_snapshot=endpoint.model_name,
                    authentication_mode_snapshot=endpoint.authentication_mode,
                    secret_alias_snapshot=endpoint.secret_alias,
                    api_key_ciphertext_snapshot=endpoint.api_key_ciphertext,
                    context_window_tokens_snapshot=endpoint.context_window_tokens,
                    max_output_tokens_snapshot=endpoint.max_output_tokens,
                    reasoning_effort_snapshot=endpoint.reasoning_effort,
                    thinking_budget_tokens_snapshot=endpoint.thinking_budget_tokens,
                    per_run_token_limit_snapshot=endpoint.per_run_token_limit,
                    request_timeout_seconds_snapshot=endpoint.request_timeout_seconds,
                    concurrency_limit_snapshot=endpoint.concurrency_limit,
                    endpoint_daily_token_limit_snapshot=endpoint.daily_token_limit,
                    site_daily_token_limit_snapshot=policy.daily_token_limit,
                    estimated_input_tokens=estimate,
                    task_run_id=stable_task_run_id,
                )
        except IntegrityError:
            invocation = _existing_invocation(
                caller_type=stable_caller_type,
                caller_id=stable_caller_id,
                idempotency_key=stable_idempotency_key,
            )
            if invocation is None:
                raise
            if (
                invocation.profile_key_snapshot != stable_profile_key
                or invocation.estimated_input_tokens != estimate
                or invocation.task_run_id != stable_task_run_id
            ):
                raise AgentCommandError(
                    "agents.idempotency_conflict.v1",
                    "相同幂等标识已用于不同调用。",
                ) from None
    return invocation


def bind_agent_invocation_task_run(*, invocation_id, task_run_id) -> AgentInvocation:
    try:
        identity = normalize_ulid(invocation_id)
        stable_task_run_id = normalize_ulid(task_run_id)
    except (TypeError, ValueError):
        raise AgentCommandError(
            "agents.invocation_invalid.v1", "任务运行标识不合法。"
        ) from None
    with transaction.atomic():
        try:
            invocation = AgentInvocation.objects.select_for_update().get(pk=identity)
        except AgentInvocation.DoesNotExist:
            raise AgentCommandError(
                "agents.invocation_not_found.v1", "AGENT 调用不存在。"
            ) from None
        if invocation.state != AgentInvocation.State.PENDING:
            raise AgentCommandError(
                "agents.invocation_conflict.v1", "AGENT 调用状态冲突。"
            )
        if invocation.task_run_id not in {"", stable_task_run_id}:
            raise AgentCommandError(
                "agents.invocation_conflict.v1", "AGENT 调用已绑定其他任务。"
            )
        if not invocation.task_run_id:
            invocation.task_run_id = stable_task_run_id
            invocation.save(update_fields=("task_run_id", "updated_at"))
    return invocation


def _same_snapshot(left: AgentInvocation, right: AgentInvocation) -> bool:
    fields = (
        "profile_id",
        "prompt_revision_id",
        "endpoint_id",
        "profile_key_snapshot",
        "schema_key_snapshot",
        "prompt_sequence_snapshot",
        "prompt_sha256_snapshot",
        "endpoint_row_version_snapshot",
        "endpoint_protocol_snapshot",
        "endpoint_base_url_snapshot",
        "model_name_snapshot",
        "authentication_mode_snapshot",
        "secret_alias_snapshot",
        "api_key_ciphertext_snapshot",
        "context_window_tokens_snapshot",
        "max_output_tokens_snapshot",
        "reasoning_effort_snapshot",
        "thinking_budget_tokens_snapshot",
        "per_run_token_limit_snapshot",
        "request_timeout_seconds_snapshot",
        "concurrency_limit_snapshot",
        "endpoint_daily_token_limit_snapshot",
        "site_daily_token_limit_snapshot",
        "estimated_input_tokens",
    )
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def create_agent_invocation_from_snapshot(
    *,
    source_invocation_id,
    caller_type,
    caller_id,
    idempotency_key,
    task_run_id,
) -> AgentInvocation:
    stable_caller_type = validate_caller_type(caller_type)
    stable_caller_id = validate_bounded_identifier(caller_id)
    stable_idempotency_key = validate_idempotency_key(idempotency_key)
    try:
        source_identity = normalize_ulid(source_invocation_id)
        stable_task_run_id = normalize_ulid(task_run_id)
    except (TypeError, ValueError):
        raise AgentCommandError(
            "agents.invocation_invalid.v1", "AGENT 调用快照不合法。"
        ) from None
    try:
        source = AgentInvocation.objects.get(pk=source_identity)
    except AgentInvocation.DoesNotExist:
        raise AgentCommandError(
            "agents.invocation_not_found.v1", "AGENT 调用快照不存在。"
        ) from None
    existing = _existing_invocation(
        caller_type=stable_caller_type,
        caller_id=stable_caller_id,
        idempotency_key=stable_idempotency_key,
    )
    if existing is not None:
        if existing.task_run_id != stable_task_run_id or not _same_snapshot(
            existing, source
        ):
            raise AgentCommandError(
                "agents.idempotency_conflict.v1",
                "相同幂等标识已用于不同调用。",
            )
        return existing
    values = {
        field: getattr(source, field)
        for field in (
            "profile_key_snapshot",
            "schema_key_snapshot",
            "prompt_sequence_snapshot",
            "prompt_sha256_snapshot",
            "endpoint_row_version_snapshot",
            "endpoint_protocol_snapshot",
            "endpoint_base_url_snapshot",
            "model_name_snapshot",
            "authentication_mode_snapshot",
            "secret_alias_snapshot",
            "api_key_ciphertext_snapshot",
            "context_window_tokens_snapshot",
            "max_output_tokens_snapshot",
            "reasoning_effort_snapshot",
            "thinking_budget_tokens_snapshot",
            "per_run_token_limit_snapshot",
            "request_timeout_seconds_snapshot",
            "concurrency_limit_snapshot",
            "endpoint_daily_token_limit_snapshot",
            "site_daily_token_limit_snapshot",
            "estimated_input_tokens",
        )
    }
    try:
        with transaction.atomic():
            invocation = AgentInvocation.objects.create(
                profile_id=source.profile_id,
                prompt_revision_id=source.prompt_revision_id,
                endpoint_id=source.endpoint_id,
                caller_type=stable_caller_type,
                caller_id=stable_caller_id,
                idempotency_key=stable_idempotency_key,
                task_run_id=stable_task_run_id,
                **values,
            )
    except IntegrityError:
        invocation = _existing_invocation(
            caller_type=stable_caller_type,
            caller_id=stable_caller_id,
            idempotency_key=stable_idempotency_key,
        )
        if (
            invocation is None
            or invocation.task_run_id != stable_task_run_id
            or not _same_snapshot(invocation, source)
        ):
            raise AgentCommandError(
                "agents.idempotency_conflict.v1",
                "相同幂等标识已用于不同调用。",
            ) from None
    return invocation


__all__ = [
    "bind_agent_invocation_task_run",
    "create_agent_invocation",
    "create_agent_invocation_from_snapshot",
]
