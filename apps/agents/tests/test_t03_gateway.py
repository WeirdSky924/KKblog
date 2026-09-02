import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.accounts.models import Account, RoleAssignment
from apps.agents.contracts import EndpointRuntimeSettings
from apps.agents.gateway import AgentGateway, GatewayError
from apps.agents.models import (
    AgentEndpoint,
    AgentEndpointCheck,
    AgentInvocation,
    AgentProfile,
    AgentTokenLedger,
    AgentTokenReservation,
)
from apps.agents.providers.fake import (
    DeterministicFakeProviderTransport,
    ScriptedProviderTransport,
)
from apps.agents.providers.http import ProviderHttpResponse, ProviderTransportError
from apps.agents.public import (
    EndpointDraft,
    ProfileDraft,
    create_agent_endpoint,
    create_agent_invocation,
    create_agent_profile,
    save_agent_prompt_revision,
    set_agent_profile_enabled,
)
from apps.agents.schemas import (
    SchemaValidationError,
    StructuredSchema,
    ValidatedOutput,
    register_structured_schema,
)
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)

NOW = datetime(2026, 8, 16, 14, 0, tzinfo=UTC)
PUBLIC_ADDRESS = "93.184.216.34"


def _schema() -> StructuredSchema:
    def validate(value):
        if not isinstance(value, dict) or value.get("verdict") not in {
            "APPROVED",
            "REJECTED",
        }:
            raise SchemaValidationError()
        return {"verdict": value["verdict"]}

    schema = StructuredSchema(
        key="gateway-review.v1",
        provider_schema={
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["APPROVED", "REJECTED"]}
            },
            "required": ["verdict"],
            "additionalProperties": False,
        },
        validator=validate,
    )
    register_structured_schema(schema, replace=True)
    return schema


def _admin() -> Account:
    account = Account.objects.create_account(
        email=f"gateway-{uuid4()}@kaj.test", password="Valid-password-1"
    )
    RoleAssignment.objects.create(
        account=account, role=RoleAssignment.Role.ADMINISTRATOR
    )
    return account


def _configured_invocation(
    *,
    protocol=AgentEndpoint.Protocol.OPENAI_GPT,
    secret_alias="",
    api_key="",
    runtime=None,
    caller_id="document-001",
):
    _schema()
    admin = _admin()
    endpoint = create_agent_endpoint(
        actor_id=admin.id,
        draft=EndpointDraft(
            display_name=f"Gateway {protocol} {uuid4()}",
            protocol=protocol,
            base_url="https://api.example.com/v1",
            model_name="test-model",
            authentication_mode=(
                AgentEndpoint.AuthenticationMode.SECRET_ALIAS
                if secret_alias
                else (
                    AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY
                    if api_key
                    else AgentEndpoint.AuthenticationMode.NONE
                )
            ),
            secret_alias=secret_alias,
            api_key=api_key,
            enabled=True,
            runtime=runtime or EndpointRuntimeSettings(),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile = create_agent_profile(
        actor_id=admin.id,
        draft=ProfileDraft(
            key=f"knowledge-review-{uuid4().hex[:8]}",
            display_name="知识审核",
            purpose=AgentProfile.Purpose.KNOWLEDGE_REVIEW,
            endpoint_id=endpoint.id,
            schema_key="gateway-review.v1",
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    save_agent_prompt_revision(
        actor_id=admin.id,
        profile_id=profile.id,
        markdown_source="审核资料：{{ document_block }}",
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    now = NOW
    AgentEndpointCheck.objects.create(
        endpoint=endpoint,
        requested_by_id=admin.id,
        idempotency_key=f"test-capability:{uuid4()}",
        state=AgentEndpointCheck.State.SUCCEEDED,
        endpoint_row_version_snapshot=endpoint.row_version,
        protocol_snapshot=endpoint.protocol,
        base_url_snapshot=endpoint.base_url,
        model_name_snapshot=endpoint.model_name,
        schema_key_snapshot=profile.schema_key,
        capability_strategy="native",
        capability_state="SCHEMA_SUPPORTED",
        authentication_mode_snapshot=endpoint.authentication_mode,
        secret_alias_snapshot=endpoint.secret_alias,
        api_key_ciphertext_snapshot=endpoint.api_key_ciphertext,
        request_timeout_seconds_snapshot=endpoint.request_timeout_seconds,
        concurrency_limit_snapshot=endpoint.concurrency_limit,
        endpoint_daily_token_limit_snapshot=endpoint.daily_token_limit,
        site_daily_token_limit_snapshot=5_000_000,
        token_budget=2_048,
        attempt_count=1,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        requested_at=now,
        started_at=now,
        completed_at=now,
    )
    set_agent_profile_enabled(
        actor_id=admin.id,
        profile_id=profile.id,
        enabled=True,
        expected_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    invocation = create_agent_invocation(
        profile_key=profile.key,
        caller_type="knowledge_review",
        caller_id=caller_id,
        idempotency_key=f"review-{caller_id}",
        estimated_input_tokens=1_000,
    )
    return admin, endpoint, profile, invocation


def _gateway(transport, *, secrets=None, clock=lambda: NOW) -> AgentGateway:
    return AgentGateway(
        transport=transport,
        resolver=lambda _hostname, _port: (PUBLIC_ADDRESS,),
        secret_registry=secrets or {},
        sleeper=lambda _seconds: None,
        clock=clock,
    )


def _openai_response(value, *, input_tokens=100, output_tokens=20, usage=True):
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(value),
                }
            }
        ]
    }
    if usage:
        payload["usage"] = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    return ProviderHttpResponse(200, {}, json.dumps(payload).encode())


def _openai_terminal_response(*, refusal=False, incomplete=False):
    message = {"role": "assistant", "content": None}
    if refusal:
        message = {"role": "assistant", "content": None, "refusal": "policy"}
    payload = {
        "choices": [
            {
                "message": message,
                "finish_reason": "length" if incomplete else "stop",
            }
        ]
    }
    return ProviderHttpResponse(200, {}, json.dumps(payload).encode())


@pytest.mark.parametrize(
    "protocol",
    (
        AgentEndpoint.Protocol.OPENAI_GPT,
        AgentEndpoint.Protocol.OPENAI_DEEPSEEK,
        AgentEndpoint.Protocol.ANTHROPIC,
    ),
)
def test_gateway_executes_three_protocols_and_settles_trusted_usage(protocol) -> None:
    _, _, _, invocation = _configured_invocation(protocol=protocol)
    transport = DeterministicFakeProviderTransport(
        value={"verdict": "APPROVED"}, input_tokens=100, output_tokens=20
    )
    result = _gateway(transport).execute(
        invocation_id=invocation.id,
        input_blocks=("不可信资料",),
        now=NOW,
    )
    assert result.value == {"verdict": "APPROVED"}
    assert isinstance(result.validated_output, ValidatedOutput)
    assert result.validated_output.schema_key == "gateway-review.v1"
    assert result.settled_tokens == 120
    assert result.attempt_count == 1
    assert transport.call_count == 1
    invocation.refresh_from_db()
    assert invocation.state == AgentInvocation.State.SUCCEEDED
    assert invocation.total_tokens == 120
    attempt = invocation.attempts.get(sequence=1)
    assert attempt.phase == "ACCEPTED"
    assert attempt.strategy in {"native", "tool"}
    assert attempt.adapter_version.startswith("langchain-")
    assert attempt.completed_at is not None
    reservation = invocation.token_reservation
    assert reservation.status == AgentTokenReservation.Status.SETTLED
    assert reservation.settled_tokens == 120


def test_gateway_uses_custom_api_key_ciphertext_snapshot_for_external_call() -> None:
    _, _, _, invocation = _configured_invocation(api_key="sk-custom-gateway-key")
    transport = ScriptedProviderTransport(
        (
            DeterministicFakeProviderTransport(
                value={"verdict": "APPROVED"}, input_tokens=10, output_tokens=5
            ),
        )
    )
    result = _gateway(transport).execute(
        invocation_id=invocation.id,
        input_blocks=("资料",),
        now=NOW,
    )
    assert result.value == {"verdict": "APPROVED"}
    request = transport.last_request
    assert request is not None
    assert request.headers["Authorization"] == "Bearer sk-custom-gateway-key"
    invocation.refresh_from_db()
    assert invocation.api_key_ciphertext_snapshot
    assert "sk-custom-gateway-key" not in invocation.api_key_ciphertext_snapshot


def test_missing_usage_keeps_full_conservative_reservation() -> None:
    _, _, _, invocation = _configured_invocation()
    transport = DeterministicFakeProviderTransport(
        value={"verdict": "APPROVED"}, include_usage=False
    )
    result = _gateway(transport).execute(
        invocation_id=invocation.id,
        input_blocks=("资料",),
        now=NOW,
    )
    assert result.settled_tokens == invocation.per_run_token_limit_snapshot
    assert invocation.per_run_token_limit_snapshot == 500_000


def test_quota_failure_makes_zero_external_calls() -> None:
    _, endpoint, _, invocation = _configured_invocation(
        runtime=EndpointRuntimeSettings(endpoint_daily_token_limit=500_000)
    )
    usage_date = timezone.localdate(NOW)
    AgentTokenLedger.objects.create(
        scope=AgentTokenLedger.Scope.SITE,
        usage_date=usage_date,
        settled_tokens=100_000,
    )
    AgentTokenLedger.objects.create(
        scope=AgentTokenLedger.Scope.ENDPOINT,
        endpoint=endpoint,
        usage_date=usage_date,
        settled_tokens=100_000,
    )
    transport = DeterministicFakeProviderTransport(value={"verdict": "APPROVED"})
    with pytest.raises(GatewayError) as rejected:
        _gateway(transport).execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            now=NOW,
        )
    assert rejected.value.code == "agents.quota_exhausted.v1"
    assert rejected.value.retryable is False
    assert transport.call_count == 0
    invocation.refresh_from_db()
    assert invocation.state == AgentInvocation.State.PENDING


def test_transient_failures_retry_then_succeed() -> None:
    _, _, _, invocation = _configured_invocation()
    transport = ScriptedProviderTransport(
        (
            ProviderTransportError("agents.request_network_failed.v1", retryable=True),
            ProviderTransportError("agents.request_timeout.v1", retryable=True),
            _openai_response({"verdict": "APPROVED"}),
        )
    )
    result = _gateway(transport).execute(
        invocation_id=invocation.id,
        input_blocks=("资料",),
        now=NOW,
    )
    assert result.attempt_count == 3
    assert result.settled_tokens == invocation.per_run_token_limit_snapshot
    assert transport.call_count == 3
    assert invocation.token_reservation.lease_expires_at == NOW + timedelta(seconds=396)


def test_invocation_completion_uses_the_terminal_wall_clock_time() -> None:
    _, _, _, invocation = _configured_invocation(caller_id="duration-readback")
    completed_at = NOW + timedelta(seconds=7)
    clock_values = iter((NOW, completed_at))
    transport = DeterministicFakeProviderTransport(value={"verdict": "APPROVED"})

    _gateway(transport, clock=lambda: next(clock_values)).execute(
        invocation_id=invocation.id,
        input_blocks=("资料",),
    )

    invocation.refresh_from_db()
    assert invocation.started_at == NOW
    assert invocation.completed_at == completed_at


def test_retry_count_cannot_exceed_the_per_run_snapshot_budget() -> None:
    runtime = EndpointRuntimeSettings(
        max_output_tokens=4_000,
        per_run_token_limit=10_000,
    )
    _, _, _, invocation = _configured_invocation(runtime=runtime)
    transport = ScriptedProviderTransport(
        (
            ProviderTransportError("agents.request_network_failed.v1", retryable=True),
            ProviderTransportError("agents.request_timeout.v1", retryable=True),
            _openai_response({"verdict": "APPROVED"}),
        )
    )

    with pytest.raises(GatewayError) as failed:
        _gateway(transport).execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            now=NOW,
        )

    assert failed.value.code == "agents.request_timeout.v1"
    assert transport.call_count == 2
    invocation.refresh_from_db()
    assert invocation.state == AgentInvocation.State.FAILED
    assert invocation.token_reservation.settled_tokens == 0


def test_invalid_runtime_snapshot_is_rejected_before_external_call() -> None:
    _, _, _, invocation = _configured_invocation()
    AgentInvocation.objects.filter(pk=invocation.id).update(
        context_window_tokens_snapshot=4_096,
        max_output_tokens_snapshot=4_096,
    )
    transport = DeterministicFakeProviderTransport(value={"verdict": "APPROVED"})

    with pytest.raises(GatewayError) as failed:
        _gateway(transport).execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            now=NOW,
        )

    assert failed.value.code == "agents.configuration_snapshot_invalid.v1"
    assert failed.value.retryable is False
    assert transport.call_count == 0
    invocation.refresh_from_db()
    assert invocation.state == AgentInvocation.State.PENDING
    assert not AgentTokenReservation.objects.filter(invocation=invocation).exists()


def test_unregistered_schema_is_a_safe_non_retryable_gateway_error() -> None:
    _, _, _, invocation = _configured_invocation(caller_id="missing-schema")
    AgentInvocation.objects.filter(pk=invocation.id).update(
        schema_key_snapshot="missing-schema.v1"
    )
    transport = DeterministicFakeProviderTransport(value={"verdict": "APPROVED"})

    with pytest.raises(GatewayError) as failed:
        _gateway(transport).execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            now=NOW,
        )

    assert failed.value.code == "agents.schema_unavailable.v1"
    assert failed.value.retryable is False
    assert transport.call_count == 0
    assert not AgentTokenReservation.objects.filter(invocation=invocation).exists()


def test_final_transport_failure_is_safe_and_not_quota_charged() -> None:
    _, _, _, invocation = _configured_invocation(secret_alias="PRIMARY_GPT")
    secret = "server-secret-value"
    transport = ScriptedProviderTransport(
        (RuntimeError(secret), RuntimeError(secret), RuntimeError(secret))
    )
    gateway = _gateway(transport, secrets={"PRIMARY_GPT": secret})
    with pytest.raises(GatewayError) as failed:
        gateway.execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            now=NOW,
        )
    assert failed.value.code == "agents.request_network_failed.v1"
    assert secret not in str(failed.value)
    assert secret not in repr(gateway)
    assert transport.call_count == 3
    invocation.refresh_from_db()
    assert invocation.state == AgentInvocation.State.FAILED
    assert invocation.safe_error_code == "agents.request_network_failed.v1"
    assert invocation.token_reservation.settled_tokens == 0


def test_schema_failure_gets_one_repair_request_and_no_more() -> None:
    _, _, _, invocation = _configured_invocation()
    transport = ScriptedProviderTransport(
        (
            _openai_response({"verdict": "MAYBE"}, input_tokens=10, output_tokens=2),
            _openai_response({"verdict": "APPROVED"}, input_tokens=11, output_tokens=3),
        )
    )
    result = _gateway(transport).execute(
        invocation_id=invocation.id,
        input_blocks=("资料",),
        now=NOW,
    )
    assert result.value == {"verdict": "APPROVED"}
    assert result.attempt_count == 2
    assert result.settled_tokens == 26


def test_dynamic_output_validator_repairs_inside_harness_without_failure_charge() -> (
    None
):
    _, _, _, invocation = _configured_invocation(caller_id="dynamic-output-validator")
    transport = DeterministicFakeProviderTransport(
        value={"verdict": "APPROVED"}, input_tokens=10, output_tokens=5
    )

    def reject(_value):
        raise SchemaValidationError(
            "agents.response_semantics_invalid.v1",
            expected="learning.question_schema_invalid.v1",
        )

    with pytest.raises(GatewayError) as failed:
        _gateway(transport).execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            output_validator=reject,
            now=NOW,
        )

    assert failed.value.code == "agents.response_semantics_invalid.v1"
    assert transport.call_count == 2
    invocation.refresh_from_db()
    assert invocation.state == AgentInvocation.State.FAILED
    assert invocation.token_reservation.settled_tokens == 0


@pytest.mark.parametrize(
    ("kwargs", "state", "code", "phase"),
    (
        (
            {"refusal": True},
            AgentInvocation.State.REFUSED,
            "agents.provider_refused.v1",
            "REFUSED",
        ),
        (
            {"incomplete": True},
            AgentInvocation.State.INCOMPLETE,
            "agents.provider_incomplete.v1",
            "INCOMPLETE",
        ),
    ),
)
def test_provider_terminal_outcomes_are_not_repaired(
    kwargs, state, code, phase
) -> None:
    _, _, _, invocation = _configured_invocation(caller_id=f"terminal-{code}")
    transport = ScriptedProviderTransport((_openai_terminal_response(**kwargs),))
    with pytest.raises(GatewayError) as failed:
        _gateway(transport).execute(
            invocation_id=invocation.id,
            input_blocks=("资料",),
            now=NOW,
        )
    assert failed.value.code == code
    assert transport.call_count == 1
    invocation.refresh_from_db()
    assert invocation.state == state
    attempt = invocation.attempts.get(sequence=1)
    assert attempt.phase == phase
    assert attempt.safe_error_code == code


def test_repeated_execution_never_calls_provider_twice() -> None:
    _, _, _, invocation = _configured_invocation()
    transport = DeterministicFakeProviderTransport(value={"verdict": "APPROVED"})
    gateway = _gateway(transport)
    gateway.execute(invocation_id=invocation.id, input_blocks=("资料",), now=NOW)
    with pytest.raises(GatewayError) as repeated:
        gateway.execute(invocation_id=invocation.id, input_blocks=("资料",), now=NOW)
    assert repeated.value.code == "agents.invocation_already_completed.v1"
    assert repeated.value.retryable is False
    assert transport.call_count == 1
