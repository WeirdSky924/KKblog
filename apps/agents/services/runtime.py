from django.db import transaction
from django.utils import timezone

from apps.agents.contracts import AgentCommandError, EndpointRuntimeSettings
from apps.agents.models import (
    AgentEndpoint,
    AgentInvocation,
    AgentInvocationAttempt,
    AgentTokenReservation,
)

from .common import (
    normalize_base_url,
    validate_profile_key,
    validate_schema_key,
    validate_secret_alias,
    visible_text,
)
from .usage import release_token_reservation, settle_token_reservation


def _invalid_snapshot() -> AgentCommandError:
    return AgentCommandError(
        "agents.configuration_snapshot_invalid.v1", "AGENT 配置快照不可用。"
    )


def _validate_invocation_snapshot(invocation: AgentInvocation) -> None:
    try:
        runtime = EndpointRuntimeSettings(
            context_window_tokens=invocation.context_window_tokens_snapshot,
            max_output_tokens=invocation.max_output_tokens_snapshot,
            per_run_token_limit=invocation.per_run_token_limit_snapshot,
            request_timeout_seconds=invocation.request_timeout_seconds_snapshot,
            concurrency_limit=invocation.concurrency_limit_snapshot,
            endpoint_daily_token_limit=invocation.endpoint_daily_token_limit_snapshot,
        ).validate(site_daily_token_limit=invocation.site_daily_token_limit_snapshot)
        runtime.validate_input_estimate(invocation.estimated_input_tokens)
        if (
            invocation.endpoint_protocol_snapshot not in AgentEndpoint.Protocol.values
            or normalize_base_url(invocation.endpoint_base_url_snapshot)
            != invocation.endpoint_base_url_snapshot
            or visible_text(
                invocation.model_name_snapshot, field="模型名称", maximum=160
            )
            != invocation.model_name_snapshot
            or validate_profile_key(invocation.profile_key_snapshot)
            != invocation.profile_key_snapshot
            or validate_schema_key(invocation.schema_key_snapshot)
            != invocation.schema_key_snapshot
        ):
            raise _invalid_snapshot()
        if (
            invocation.authentication_mode_snapshot
            == AgentEndpoint.AuthenticationMode.NONE
        ):
            if (
                invocation.secret_alias_snapshot
                or invocation.api_key_ciphertext_snapshot
            ):
                raise _invalid_snapshot()
        elif (
            invocation.authentication_mode_snapshot
            == AgentEndpoint.AuthenticationMode.SECRET_ALIAS
        ):
            if invocation.api_key_ciphertext_snapshot:
                raise _invalid_snapshot()
            validate_secret_alias(invocation.secret_alias_snapshot)
        elif (
            invocation.authentication_mode_snapshot
            == AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY
        ):
            if (
                invocation.secret_alias_snapshot
                or not invocation.api_key_ciphertext_snapshot
            ):
                raise _invalid_snapshot()
        else:
            raise _invalid_snapshot()
    except AgentCommandError:
        raise _invalid_snapshot() from None

    if (
        invocation.prompt_revision.profile_id != invocation.profile_id
        or invocation.prompt_revision.sequence != invocation.prompt_sequence_snapshot
        or invocation.prompt_revision.content_sha256
        != invocation.prompt_sha256_snapshot
    ):
        raise _invalid_snapshot()


def load_invocation_for_gateway(invocation_id) -> AgentInvocation:
    try:
        invocation = AgentInvocation.objects.select_related(
            "endpoint", "prompt_revision", "profile"
        ).get(pk=invocation_id)
    except AgentInvocation.DoesNotExist:
        raise AgentCommandError(
            "agents.invocation_not_found.v1", "AGENT 调用不存在。"
        ) from None
    if invocation.state in {
        AgentInvocation.State.SUCCEEDED,
        AgentInvocation.State.FAILED,
        AgentInvocation.State.REFUSED,
        AgentInvocation.State.INCOMPLETE,
        AgentInvocation.State.CANCELLED,
    }:
        raise AgentCommandError(
            "agents.invocation_already_completed.v1", "AGENT 调用已经结束。"
        )
    if invocation.state != AgentInvocation.State.PENDING:
        raise AgentCommandError(
            "agents.invocation_conflict.v1", "AGENT 调用正在由其他执行者处理。"
        )
    _validate_invocation_snapshot(invocation)
    return invocation


def mark_invocation_running(
    *, invocation_id, started_at, input_sha256: str
) -> AgentInvocation:
    with transaction.atomic():
        try:
            invocation = AgentInvocation.objects.select_for_update().get(
                pk=invocation_id
            )
        except AgentInvocation.DoesNotExist:
            raise AgentCommandError(
                "agents.invocation_not_found.v1", "AGENT 调用不存在。"
            ) from None
        if invocation.state != AgentInvocation.State.PENDING:
            raise AgentCommandError(
                "agents.invocation_conflict.v1", "AGENT 调用状态冲突。"
            )
        invocation.state = AgentInvocation.State.RUNNING
        invocation.started_at = started_at
        invocation.input_sha256 = input_sha256
        invocation.save(
            update_fields=("state", "started_at", "input_sha256", "updated_at")
        )
    return invocation


def cancel_invocation(*, invocation_id, completed_at) -> bool:
    """Cancel a pending/running invocation and release unused reservation."""

    if not timezone.is_aware(completed_at):
        raise AgentCommandError("agents.invocation_invalid.v1", "取消时间不合法。")
    reservation_id = None
    with transaction.atomic():
        try:
            invocation = AgentInvocation.objects.select_for_update().get(
                pk=invocation_id
            )
        except AgentInvocation.DoesNotExist:
            raise AgentCommandError(
                "agents.invocation_not_found.v1", "AGENT 调用不存在。"
            ) from None
        if invocation.state == AgentInvocation.State.CANCELLED:
            return True
        if invocation.state in {
            AgentInvocation.State.SUCCEEDED,
            AgentInvocation.State.FAILED,
            AgentInvocation.State.REFUSED,
            AgentInvocation.State.INCOMPLETE,
        }:
            return False
        reservation_id = (
            AgentTokenReservation.objects.filter(invocation_id=invocation.id)
            .values_list("id", flat=True)
            .first()
        )
        invocation.state = AgentInvocation.State.CANCELLED
        invocation.completed_at = completed_at
        invocation.safe_error_code = "agents.invocation_cancelled.v1"
        invocation.save(
            update_fields=("state", "completed_at", "safe_error_code", "updated_at")
        )
        if reservation_id is not None:
            release_token_reservation(reservation_id=reservation_id)
    return True


def finalize_invocation(
    *,
    invocation_id,
    reservation_id,
    actual_tokens: int,
    state: str,
    completed_at,
    output_sha256: str,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    safe_error_code: str,
) -> AgentInvocation:
    if state not in {
        AgentInvocation.State.SUCCEEDED,
        AgentInvocation.State.FAILED,
        AgentInvocation.State.REFUSED,
        AgentInvocation.State.INCOMPLETE,
    }:
        raise AgentCommandError(
            "agents.invocation_state_invalid.v1", "AGENT 终态不合法。"
        )
    with transaction.atomic():
        try:
            invocation = AgentInvocation.objects.select_for_update().get(
                pk=invocation_id
            )
        except AgentInvocation.DoesNotExist:
            raise AgentCommandError(
                "agents.invocation_not_found.v1", "AGENT 调用不存在。"
            ) from None
        if invocation.state != AgentInvocation.State.RUNNING:
            raise AgentCommandError(
                "agents.invocation_conflict.v1", "AGENT 调用状态冲突。"
            )
        settle_token_reservation(
            reservation_id=reservation_id, actual_tokens=actual_tokens
        )
        invocation.state = state
        invocation.completed_at = completed_at
        invocation.output_sha256 = output_sha256
        invocation.input_tokens = input_tokens
        invocation.output_tokens = output_tokens
        invocation.total_tokens = total_tokens
        invocation.safe_error_code = safe_error_code
        invocation.save(
            update_fields=(
                "state",
                "completed_at",
                "output_sha256",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "safe_error_code",
                "updated_at",
            )
        )
    return invocation


def start_invocation_attempt(
    *,
    invocation: AgentInvocation,
    sequence: int,
    phase: str,
    strategy: str,
    schema,
    input_bytes: int,
    started_at,
    adapter_version: str = "v1",
) -> AgentInvocationAttempt:
    return AgentInvocationAttempt.objects.create(
        invocation=invocation,
        sequence=sequence,
        phase=phase,
        strategy=strategy,
        schema_key=schema.key,
        schema_sha256=schema.schema_sha256,
        adapter_version=adapter_version[:32],
        input_bytes=input_bytes,
        started_at=started_at,
    )


def finish_invocation_attempt(
    *,
    attempt: AgentInvocationAttempt,
    phase: str,
    completed_at,
    finish_reason: str = "",
    safe_error_code: str = "",
    output_bytes: int = 0,
    usage_trusted: bool = False,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> AgentInvocationAttempt:
    AgentInvocationAttempt.objects.filter(
        pk=attempt.pk, completed_at__isnull=True
    ).update(
        phase=phase,
        completed_at=completed_at,
        finish_reason=finish_reason[:32],
        safe_error_code=safe_error_code[:96],
        output_bytes=max(0, output_bytes),
        usage_trusted=bool(usage_trusted),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
    attempt.refresh_from_db()
    return attempt


__all__ = [
    "cancel_invocation",
    "finish_invocation_attempt",
    "finalize_invocation",
    "load_invocation_for_gateway",
    "mark_invocation_running",
    "start_invocation_attempt",
]
