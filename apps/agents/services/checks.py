import re
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agents.contracts import AgentCommandError
from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentProfile,
    AgentSitePolicy,
    AgentTokenReservation,
)
from apps.core.ids import normalize_ulid
from apps.operations.public import RetryableTaskError, record_audit_entry

from .common import (
    require_administrator,
    uuid_value,
    validate_idempotency_key,
    validate_profile_key,
    validate_schema_key,
)
from .usage import reserve_endpoint_check_tokens, settle_token_reservation

if TYPE_CHECKING:
    from apps.agents.gateway import AgentGateway, EndpointProbeInput

CONNECTION_CHECK_COOLDOWN_SECONDS = 60
CONNECTION_CHECK_TOKEN_BUDGET = 2_048
_SAFE_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*\Z")


def _aware_now(value):
    current = value or timezone.now()
    if not timezone.is_aware(current):
        raise AgentCommandError(
            "agents.endpoint_check_invalid.v1", "连接检查时间不合法。"
        )
    return current


def _existing_check(*, idempotency_key: str, actor_id, endpoint_id):
    existing = AgentEndpointCheck.objects.filter(
        idempotency_key=idempotency_key
    ).first()
    if existing is None:
        return None
    if existing.requested_by_id != actor_id or existing.endpoint_id != endpoint_id:
        raise AgentCommandError(
            "agents.idempotency_conflict.v1", "相同幂等标识已用于其他连接检查。"
        )
    return existing


def request_agent_endpoint_check(
    *,
    actor_id,
    endpoint_id,
    expected_endpoint_version,
    idempotency_key,
    dispatcher: Callable[[str], None],
    trace_code,
    client_ip,
    profile_key: str = "",
    schema_key: str = "",
    now=None,
) -> AgentEndpointCheck:
    actor = require_administrator(actor_id)
    identity = uuid_value(
        endpoint_id,
        code="agents.endpoint_not_found.v1",
        message="Endpoint 不存在。",
    )
    stable_key = validate_idempotency_key(idempotency_key)
    current = _aware_now(now)
    if (
        isinstance(expected_endpoint_version, bool)
        or not isinstance(expected_endpoint_version, int)
        or expected_endpoint_version < 1
        or not callable(dispatcher)
    ):
        raise AgentCommandError(
            "agents.endpoint_check_invalid.v1", "连接检查请求不合法。"
        )
    existing = _existing_check(
        idempotency_key=stable_key,
        actor_id=actor,
        endpoint_id=identity,
    )
    if existing is not None:
        return existing
    if not isinstance(profile_key, str) or len(profile_key) > 64:
        raise AgentCommandError(
            "agents.endpoint_check_invalid.v1", "AGENT 标识不合法。"
        )
    if profile_key:
        stable_profile_key = validate_profile_key(profile_key)
        profile_schema = (
            AgentProfile.objects.filter(
                key=stable_profile_key,
                endpoint_id=identity,
                endpoint__enabled=True,
                current_prompt__isnull=False,
            )
            .values_list("schema_key", flat=True)
            .first()
        )
        if profile_schema is None:
            raise AgentCommandError(
                "agents.profile_unavailable.v1",
                "所选 AGENT 不属于这个 Endpoint 或尚未准备完成。",
            )
        if schema_key and schema_key != profile_schema:
            raise AgentCommandError(
                "agents.endpoint_check_invalid.v1", "AGENT schema 与选择不一致。"
            )
        schema_key = profile_schema
    elif schema_key:
        schema_key = validate_schema_key(schema_key)
    if not isinstance(schema_key, str) or len(schema_key) > 96:
        raise AgentCommandError(
            "agents.endpoint_check_invalid.v1", "结构化 schema 标识不合法。"
        )
    try:
        with transaction.atomic():
            policy, _ = AgentSitePolicy.objects.select_for_update().get_or_create(pk=1)
            try:
                endpoint = AgentEndpoint.objects.select_for_update().get(pk=identity)
            except AgentEndpoint.DoesNotExist:
                raise AgentCommandError(
                    "agents.endpoint_not_found.v1", "Endpoint 不存在。"
                ) from None
            if endpoint.row_version != expected_endpoint_version:
                raise AgentCommandError(
                    "agents.configuration_conflict.v1", "Endpoint 已被其他操作修改。"
                )
            if AgentEndpointCheck.objects.filter(
                endpoint=endpoint,
                requested_at__gt=current
                - timedelta(seconds=CONNECTION_CHECK_COOLDOWN_SECONDS),
            ).exists():
                raise AgentCommandError(
                    "agents.check_rate_limited.v1", "请稍后再检查这个 Endpoint。"
                )
            check = AgentEndpointCheck.objects.create(
                endpoint=endpoint,
                requested_by_id=actor,
                idempotency_key=stable_key,
                endpoint_row_version_snapshot=endpoint.row_version,
                protocol_snapshot=endpoint.protocol,
                base_url_snapshot=endpoint.base_url,
                model_name_snapshot=endpoint.model_name,
                reasoning_effort_snapshot=endpoint.reasoning_effort,
                thinking_budget_tokens_snapshot=endpoint.thinking_budget_tokens,
                schema_key_snapshot=schema_key,
                authentication_mode_snapshot=endpoint.authentication_mode,
                secret_alias_snapshot=endpoint.secret_alias,
                api_key_ciphertext_snapshot=endpoint.api_key_ciphertext,
                request_timeout_seconds_snapshot=endpoint.request_timeout_seconds,
                concurrency_limit_snapshot=endpoint.concurrency_limit,
                endpoint_daily_token_limit_snapshot=endpoint.daily_token_limit,
                site_daily_token_limit_snapshot=policy.daily_token_limit,
                token_budget=CONNECTION_CHECK_TOKEN_BUDGET,
                requested_at=current,
            )
            record_audit_entry(
                action="agents.endpoint_check.request",
                actor_id=actor,
                target_id=check.id,
                trace_code=trace_code,
                client_ip=client_ip,
                before={},
                after={
                    "endpoint_id": str(endpoint.id),
                    "endpoint_row_version": endpoint.row_version,
                    "reservation_units": check.token_budget,
                    "state": check.state,
                },
                summary="Request agent endpoint check",
            )
            transaction.on_commit(lambda: dispatcher(check.id))
    except IntegrityError as exc:
        repeated = _existing_check(
            idempotency_key=stable_key,
            actor_id=actor,
            endpoint_id=identity,
        )
        if repeated is not None:
            return repeated
        raise AgentCommandError(
            "agents.endpoint_check_conflict.v1", "连接检查请求冲突。"
        ) from exc
    return check


def _claim_check(*, check_id, task_run_id: str, now) -> AgentEndpointCheck:
    identity = normalize_ulid(check_id)
    run_id = normalize_ulid(task_run_id)
    with transaction.atomic():
        try:
            check = AgentEndpointCheck.objects.select_for_update().get(pk=identity)
        except AgentEndpointCheck.DoesNotExist:
            raise AgentCommandError(
                "agents.endpoint_check_not_found.v1", "连接检查不存在。"
            ) from None
        if check.state in {
            AgentEndpointCheck.State.SUCCEEDED,
            AgentEndpointCheck.State.FAILED,
        }:
            return check
        if check.state == AgentEndpointCheck.State.PENDING:
            check.state = AgentEndpointCheck.State.RUNNING
            check.started_at = now
            check.task_run_id = run_id
        elif check.task_run_id != run_id:
            raise AgentCommandError(
                "agents.endpoint_check_conflict.v1", "连接检查正在由其他任务处理。"
            )
        if check.attempt_count >= 3:
            raise AgentCommandError(
                "agents.endpoint_check_conflict.v1", "连接检查已达到尝试上限。"
            )
        check.attempt_count += 1
        check.save(
            update_fields=(
                "state",
                "started_at",
                "task_run_id",
                "attempt_count",
                "updated_at",
            )
        )
    return check


def _probe_input(check: AgentEndpointCheck) -> "EndpointProbeInput":
    from apps.agents.gateway import EndpointProbeInput

    return EndpointProbeInput(
        protocol=check.protocol_snapshot,
        base_url=check.base_url_snapshot,
        model_name=check.model_name_snapshot,
        authentication_mode=check.authentication_mode_snapshot,
        secret_alias=check.secret_alias_snapshot,
        api_key_ciphertext=check.api_key_ciphertext_snapshot,
        timeout_seconds=check.request_timeout_seconds_snapshot,
        token_budget=check.token_budget,
        schema_key=check.schema_key_snapshot,
        reasoning_effort=check.reasoning_effort_snapshot,
        thinking_budget_tokens=check.thinking_budget_tokens_snapshot,
    )


def _completed_time(started_at, current):
    return max(started_at or current, current, timezone.now())


def execute_agent_endpoint_check(
    *, check_id, task_run_id, gateway: "AgentGateway", now=None
) -> AgentEndpointCheck:
    from apps.agents.gateway import AgentGateway, GatewayError

    current = _aware_now(now)
    if not isinstance(gateway, AgentGateway):
        raise AgentCommandError(
            "agents.endpoint_check_invalid.v1", "连接检查运行器不合法。"
        )
    check = _claim_check(check_id=check_id, task_run_id=task_run_id, now=current)
    if check.state != AgentEndpointCheck.State.RUNNING:
        return check
    reservation = reserve_endpoint_check_tokens(
        check_id=check.id,
        idempotency_key=f"endpoint-check:{check.id}",
        lease_expires_at=current + timedelta(hours=1),
        now=current,
    )
    try:
        probe = gateway.probe_endpoint(_probe_input(check))
    except GatewayError as error:
        with transaction.atomic():
            check = AgentEndpointCheck.objects.select_for_update().get(pk=check.id)
            check.usage_uncertain = True
            check.safe_error_code = error.code
            check.save(
                update_fields=("usage_uncertain", "safe_error_code", "updated_at")
            )
        if error.retryable:
            raise RetryableTaskError(error.code) from None
        return mark_agent_endpoint_check_final_failed(
            check_id=check.id,
            safe_error_code=error.code,
            completed_at=_completed_time(check.started_at, current),
        )

    with transaction.atomic():
        check = AgentEndpointCheck.objects.select_for_update().get(pk=check.id)
        if check.state != AgentEndpointCheck.State.RUNNING:
            return check
        trusted = not check.usage_uncertain and probe.total_tokens is not None
        settle_token_reservation(
            reservation_id=reservation.id,
            actual_tokens=probe.total_tokens if trusted else check.token_budget,
        )
        check.state = AgentEndpointCheck.State.SUCCEEDED
        check.completed_at = _completed_time(check.started_at, current)
        check.input_tokens = probe.input_tokens if trusted else None
        check.output_tokens = probe.output_tokens if trusted else None
        check.total_tokens = probe.total_tokens if trusted else None
        check.safe_error_code = ""
        check.capability_strategy = probe.strategy
        check.capability_adapter_version = probe.adapter_version[:32]
        check.capability_state = (
            "SCHEMA_SUPPORTED" if probe.schema_key else "CONNECTIVITY_ONLY"
        )
        check.save()
    return check


def mark_agent_endpoint_check_final_failed(
    *, check_id, safe_error_code: str, completed_at
) -> AgentEndpointCheck:
    identity = normalize_ulid(check_id)
    if not _SAFE_ERROR_CODE.fullmatch(safe_error_code) or not timezone.is_aware(
        completed_at
    ):
        raise AgentCommandError(
            "agents.endpoint_check_invalid.v1", "连接检查终态不合法。"
        )
    with transaction.atomic():
        try:
            check = AgentEndpointCheck.objects.select_for_update().get(pk=identity)
        except AgentEndpointCheck.DoesNotExist:
            raise AgentCommandError(
                "agents.endpoint_check_not_found.v1", "连接检查不存在。"
            ) from None
        if check.state == AgentEndpointCheck.State.SUCCEEDED:
            raise AgentCommandError(
                "agents.endpoint_check_conflict.v1", "连接检查已经成功完成。"
            )
        if check.state == AgentEndpointCheck.State.FAILED:
            return check
        reservation = AgentTokenReservation.objects.filter(endpoint_check=check).first()
        if reservation is not None:
            settle_token_reservation(
                reservation_id=reservation.id,
                actual_tokens=0,
            )
        check.state = AgentEndpointCheck.State.FAILED
        check.started_at = check.started_at or completed_at
        check.completed_at = max(check.started_at, completed_at)
        check.usage_uncertain = reservation is not None
        check.safe_error_code = safe_error_code
        check.save()
    return check


__all__ = [
    "CONNECTION_CHECK_COOLDOWN_SECONDS",
    "CONNECTION_CHECK_TOKEN_BUDGET",
    "execute_agent_endpoint_check",
    "mark_agent_endpoint_check_final_failed",
    "request_agent_endpoint_check",
]
