from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256

from django.conf import settings
from django.utils import timezone

from apps.agents.contracts import (
    MAX_REQUEST_TIMEOUT_SECONDS,
    AgentCommandError,
)
from apps.agents.credentials import AgentCredentialError, decrypt_api_key
from apps.agents.models import AgentEndpoint, AgentInvocation
from apps.agents.providers.adapters import (
    ProviderAdapterInput,
    ProviderResponseError,
)
from apps.agents.providers.http import (
    MAX_PROVIDER_RESPONSE_BYTES,
    ProviderNetworkPolicy,
    ProviderTransportError,
    Resolver,
    SafeProviderHttpClient,
    Transport,
    default_provider_transport,
    system_provider_resolver,
)
from apps.agents.providers.langchain_adapter import (
    adapter_version_for_protocol,
    invoke_langchain,
    probe_langchain_connectivity,
)
from apps.agents.schemas import (
    SchemaValidationError,
    StructuredSchema,
    ValidatedOutput,
    structured_schema,
)
from apps.agents.services.runtime import (
    cancel_invocation,
    finalize_invocation,
    finish_invocation_attempt,
    load_invocation_for_gateway,
    mark_invocation_running,
    start_invocation_attempt,
)
from apps.agents.services.usage import reserve_invocation_tokens

_VARIABLE = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")
_MAX_INPUT_BLOCKS = 128
_MAX_INPUT_BYTES = 4 * 1024 * 1024
_RETRY_DELAYS = (0, 1, 5)
_RETRYABLE_COMMAND_CODES = frozenset(
    {
        "agents.concurrency_exhausted.v1",
    }
)
_REPAIRABLE_PROVIDER_CODES = frozenset(
    {
        "agents.response_invalid.v1",
        "agents.response_duplicate_key.v1",
        "agents.response_unknown_tool.v1",
        "agents.response_multiple_outputs.v1",
        "agents.response_unexpected_tool.v1",
        "agents.response_not_object.v1",
    }
)


class GatewayError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class GatewayResult:
    invocation_id: str
    validated_output: ValidatedOutput
    settled_tokens: int
    attempt_count: int

    @property
    def value(self) -> Mapping[str, object]:
        """Compatibility view; business consumers should use validated_output."""
        return self.validated_output.value


def _strategy_for(protocol: str, schema: StructuredSchema) -> str:
    if (
        protocol == AgentEndpoint.Protocol.OPENAI_GPT
        and "native" in schema.allowed_strategies
    ):
        return "native"
    if (
        protocol
        in {
            AgentEndpoint.Protocol.OPENAI_DEEPSEEK,
            AgentEndpoint.Protocol.ANTHROPIC,
        }
        and "tool" in schema.allowed_strategies
    ):
        return "tool"
    if "json_best_effort" in schema.allowed_strategies:
        return "json_best_effort"
    raise GatewayError("agents.structured_output_unsupported.v1")


def _validated_provider_value(parsed, *, strategy: str, tool_name: str):
    if strategy == "tool":
        if len(parsed.tool_calls) != 1:
            raise ProviderResponseError("agents.response_multiple_outputs.v1")
        if parsed.tool_calls[0].name != tool_name:
            raise ProviderResponseError("agents.response_unknown_tool.v1")
        return parsed.tool_calls[0].arguments
    if parsed.tool_calls:
        raise ProviderResponseError("agents.response_unexpected_tool.v1")
    return parsed.value


def _safe_repair_feedback(error: SchemaValidationError) -> str:
    parts = [error.code]
    if error.path:
        parts.append(f"path={error.path[:160]}")
    if error.expected:
        parts.append(f"expected={error.expected[:120]}")
    if error.actual:
        parts.append(f"actual={error.actual[:120]}")
    return "; ".join(parts)


@dataclass(frozen=True, slots=True)
class EndpointProbeInput:
    protocol: str
    base_url: str
    model_name: str
    authentication_mode: str
    secret_alias: str
    timeout_seconds: int
    token_budget: int
    api_key_ciphertext: str = ""
    schema_key: str = ""
    reasoning_effort: str = ""
    thinking_budget_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class EndpointProbeResult:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    strategy: str = ""
    schema_key: str = ""
    adapter_version: str = ""


def _validate_probe_response(value: object) -> Mapping[str, object]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"ok"}
        or value["ok"] is not True
    ):
        raise SchemaValidationError()
    return {"ok": True}


_PROBE_SCHEMA = StructuredSchema(
    key="agent-endpoint-check.v1",
    provider_schema={
        "type": "object",
        "properties": {"ok": {"type": "boolean", "const": True}},
        "required": ["ok"],
        "additionalProperties": False,
    },
    validator=_validate_probe_response,
)


def _command_error(error: AgentCommandError) -> GatewayError:
    return GatewayError(
        error.code,
        retryable=error.code in _RETRYABLE_COMMAND_CODES,
    )


def _validated_blocks(values: object) -> tuple[str, ...]:
    if (
        not isinstance(values, (list, tuple))
        or not 1 <= len(values) <= _MAX_INPUT_BLOCKS
    ):
        raise GatewayError("agents.input_invalid.v1")
    result = []
    total = 0
    for value in values:
        if not isinstance(value, str) or "\x00" in value:
            raise GatewayError("agents.input_invalid.v1")
        total += len(value.encode("utf-8"))
        if total > _MAX_INPUT_BYTES:
            raise GatewayError("agents.request_too_large.v1")
        result.append(value)
    return tuple(result)


def _variables(
    values: Mapping[str, object] | None, *, block_count: int
) -> dict[str, str]:
    result = {
        "document_block": "[supplied separately as untrusted material]",
        "block_index": "1",
        "block_count": str(block_count),
        "knowledge_points": "[supplied separately as untrusted material]",
        "question_types": "[configured by the caller]",
        "question_limit": "[configured by the caller]",
        "tag_candidates": "[bounded candidates supplied by the caller]",
        "article_title": "[article title supplied by the caller]",
        "article_summary": "[article summary supplied by the caller]",
        "article_tags": "[article tags supplied by the caller]",
        "section_heading": "[article heading supplied by the caller]",
        "selected_text": "[selected text supplied by the caller]",
    }
    if values is None:
        return result
    if not isinstance(values, Mapping) or len(values) > len(result):
        raise GatewayError("agents.prompt_variables_invalid.v1")
    for key, value in values.items():
        maximum = 10_000 if key == "selected_text" else 500
        if (
            key not in result
            or not isinstance(value, str)
            or not 1 <= len(value) <= maximum
            or "\x00" in value
        ):
            raise GatewayError("agents.prompt_variables_invalid.v1")
        result[key] = value
    return result


def _render_prompt(source: str, variables: Mapping[str, str]) -> str:
    invalid = False

    def replace(match):
        nonlocal invalid
        value = variables.get(match.group(1))
        if value is None:
            invalid = True
            return ""
        return value

    rendered = _VARIABLE.sub(replace, source)
    if invalid or "{{" in rendered or "}}" in rendered:
        raise GatewayError("agents.prompt_variables_invalid.v1")
    return rendered


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class AgentGateway:
    def __init__(
        self,
        *,
        transport: Transport,
        resolver: Resolver,
        secret_registry: Mapping[str, str],
        internal_allowlist: tuple[str, ...] = (),
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        if (
            not callable(transport)
            or not callable(resolver)
            or not callable(sleeper)
            or not callable(clock)
        ):
            raise ValueError("Invalid AgentGateway dependency")
        self._secrets = self._validated_secrets(secret_registry)
        self._client = SafeProviderHttpClient(
            policy=ProviderNetworkPolicy(internal_allowlist=internal_allowlist),
            resolver=resolver,
            transport=transport,
            monotonic=monotonic,
        )
        self._sleeper = sleeper
        self._clock = clock

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured=True)"

    def _invoke_provider(
        self,
        provider_input: ProviderAdapterInput,
        *,
        timeout_seconds: int,
        max_response_bytes: int,
    ):
        """Invoke the sole LangChain-backed provider owner."""
        return invoke_langchain(
            provider_input,
            safe_client=self._client,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )

    @staticmethod
    def _validated_secrets(values: Mapping[str, str]) -> dict[str, str]:
        if not isinstance(values, Mapping) or len(values) > 64:
            raise ValueError("Invalid AgentGateway secret registry")
        result = {}
        for alias, value in values.items():
            if (
                not isinstance(alias, str)
                or not isinstance(value, str)
                or not value
                or "\x00" in value
            ):
                raise ValueError("Invalid AgentGateway secret registry")
            result[alias] = value
        return result

    def _secret_for(
        self, authentication_mode: str, secret_alias: str, api_key_ciphertext: str = ""
    ) -> str | None:
        if authentication_mode == AgentEndpoint.AuthenticationMode.NONE:
            return None
        if authentication_mode == AgentEndpoint.AuthenticationMode.CUSTOM_API_KEY:
            try:
                return decrypt_api_key(api_key_ciphertext)
            except AgentCredentialError:
                raise GatewayError("agents.credential_unavailable.v1") from None
        if authentication_mode != AgentEndpoint.AuthenticationMode.SECRET_ALIAS:
            raise GatewayError("agents.configuration_snapshot_invalid.v1")
        secret = self._secrets.get(secret_alias)
        if secret is None:
            raise GatewayError("agents.secret_unavailable.v1")
        return secret

    def _secret(self, invocation: AgentInvocation) -> str | None:
        return self._secret_for(
            invocation.authentication_mode_snapshot,
            invocation.secret_alias_snapshot,
            invocation.api_key_ciphertext_snapshot,
        )

    def probe_endpoint(self, probe: EndpointProbeInput) -> EndpointProbeResult:
        if (
            not isinstance(probe, EndpointProbeInput)
            or probe.protocol not in AgentEndpoint.Protocol.values
            or isinstance(probe.timeout_seconds, bool)
            or not 10 <= probe.timeout_seconds <= MAX_REQUEST_TIMEOUT_SECONDS
            or isinstance(probe.token_budget, bool)
            or not 256 <= probe.token_budget <= 10_000
        ):
            raise GatewayError("agents.configuration_snapshot_invalid.v1")
        secret = self._secret_for(
            probe.authentication_mode,
            probe.secret_alias,
            probe.api_key_ciphertext,
        )
        if not probe.schema_key:
            provider_input = ProviderAdapterInput(
                protocol=probe.protocol,
                base_url=probe.base_url,
                model_name=probe.model_name,
                admin_prompt="Connectivity check only.",
                input_blocks=("connection-check",),
                max_output_tokens=64,
                schema=_PROBE_SCHEMA,
                strategy="native",
                reasoning_effort=probe.reasoning_effort,
                thinking_budget_tokens=probe.thinking_budget_tokens,
                secret=secret,
            )
            try:
                parsed = probe_langchain_connectivity(
                    provider_input,
                    safe_client=self._client,
                    timeout_seconds=probe.timeout_seconds,
                    max_response_bytes=65_536,
                )
            except (ProviderTransportError, ProviderResponseError) as error:
                raise GatewayError(error.code, retryable=error.retryable) from None
            usage = parsed.usage
            if usage is None or usage.total_tokens > probe.token_budget:
                return EndpointProbeResult(
                    None,
                    None,
                    None,
                    strategy="connectivity",
                    adapter_version=parsed.adapter_version,
                )
            return EndpointProbeResult(
                usage.input_tokens,
                usage.output_tokens,
                usage.total_tokens,
                strategy="connectivity",
                adapter_version=parsed.adapter_version,
            )
        probe_schema = _PROBE_SCHEMA
        try:
            probe_schema = structured_schema(probe.schema_key)
        except SchemaValidationError as error:
            raise GatewayError(error.code) from None
        provider_input = ProviderAdapterInput(
            protocol=probe.protocol,
            base_url=probe.base_url,
            model_name=probe.model_name,
            admin_prompt=(
                "This is an administrator-requested capability check. "
                + (
                    "Return one minimally valid synthetic object matching the supplied schema. "
                    "Use placeholder values only; do not use external data."
                )
            ),
            input_blocks=("connection-check",),
            max_output_tokens=64,
            schema=probe_schema,
            strategy=_strategy_for(probe.protocol, probe_schema),
            reasoning_effort=probe.reasoning_effort,
            thinking_budget_tokens=probe.thinking_budget_tokens,
            output_tool_name="endpoint_probe",
            secret=secret,
        )
        try:
            parsed = self._invoke_provider(
                provider_input,
                timeout_seconds=probe.timeout_seconds,
                max_response_bytes=65_536,
            )
            candidate = _validated_provider_value(
                parsed,
                strategy=_strategy_for(probe.protocol, probe_schema),
                tool_name="endpoint_probe",
            )
            probe_schema.validate(candidate)
        except (ProviderTransportError, ProviderResponseError) as error:
            raise GatewayError(error.code, retryable=error.retryable) from None
        except SchemaValidationError as error:
            raise GatewayError(error.code) from None
        usage = parsed.usage
        if usage is None or usage.total_tokens > probe.token_budget:
            return EndpointProbeResult(
                None,
                None,
                None,
                strategy=_strategy_for(probe.protocol, probe_schema),
                schema_key=probe.schema_key,
                adapter_version=parsed.adapter_version,
            )
        return EndpointProbeResult(
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
            strategy=_strategy_for(probe.protocol, probe_schema),
            schema_key=probe.schema_key,
            adapter_version=parsed.adapter_version,
        )

    def execute(
        self,
        *,
        invocation_id,
        input_blocks,
        prompt_variables: Mapping[str, object] | None = None,
        output_validator: Callable[[Mapping[str, object]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        now=None,
        lease_seconds: int = 300,
    ) -> GatewayResult:
        current = now or self._clock()
        if (
            not timezone.is_aware(current)
            or isinstance(lease_seconds, bool)
            or not 30 <= lease_seconds <= 3600
            or (output_validator is not None and not callable(output_validator))
            or (cancel_check is not None and not callable(cancel_check))
        ):
            raise GatewayError("agents.invocation_invalid.v1")
        blocks = _validated_blocks(input_blocks)
        try:
            invocation = load_invocation_for_gateway(invocation_id)
        except AgentCommandError as error:
            raise _command_error(error) from None
        try:
            schema = structured_schema(invocation.schema_key_snapshot)
        except SchemaValidationError as error:
            raise GatewayError(error.code) from None
        admin_prompt = _render_prompt(
            invocation.prompt_revision.markdown_source,
            _variables(prompt_variables, block_count=len(blocks)),
        )
        if output_validator is not None:
            admin_prompt = (
                "动态领域约束：调用方会逐项验证输出。严格遵守输入和 schema 规定的字段、"
                "业务不变量以及数量上限；不要虚构、重复或为了凑数生成内容。\n\n"
                + admin_prompt
            )
        secret = self._secret(invocation)
        max_attempts = self._max_provider_attempts(invocation)
        worst_case_seconds = (
            max_attempts * invocation.request_timeout_seconds_snapshot
            + sum(_RETRY_DELAYS[1:max_attempts])
            + 30
        )
        try:
            reservation = reserve_invocation_tokens(
                invocation_id=invocation.id,
                requested_tokens=invocation.per_run_token_limit_snapshot,
                idempotency_key=f"gateway:{invocation.id}",
                lease_expires_at=current
                + timedelta(seconds=max(lease_seconds, worst_case_seconds)),
                now=current,
            )
            mark_invocation_running(
                invocation_id=invocation.id,
                started_at=current,
                input_sha256=_digest(blocks),
            )
        except AgentCommandError as error:
            raise _command_error(error) from None

        if cancel_check is not None and cancel_check():
            cancel_invocation(invocation_id=invocation.id, completed_at=current)
            raise GatewayError("agents.invocation_cancelled.v1")

        return self._call_provider(
            invocation=invocation,
            reservation=reservation,
            blocks=blocks,
            admin_prompt=admin_prompt,
            secret=secret,
            schema=schema,
            started_at=current,
            max_attempts=max_attempts,
            output_validator=output_validator,
            cancel_check=cancel_check,
        )

    def _call_provider(
        self,
        *,
        invocation,
        reservation,
        blocks,
        admin_prompt,
        secret,
        schema,
        started_at,
        max_attempts,
        output_validator,
        cancel_check,
    ) -> GatewayResult:
        strategy = _strategy_for(invocation.endpoint_protocol_snapshot, schema)
        attempts = 0
        repair_used = False
        repair_feedback = ""
        usage_trusted = True
        usage = [0, 0, 0]
        last_error = GatewayError("agents.provider_failed.v1")
        while attempts < max_attempts:
            if cancel_check is not None and cancel_check():
                cancel_invocation(
                    invocation_id=invocation.id,
                    completed_at=self._clock(),
                )
                raise GatewayError("agents.invocation_cancelled.v1")
            if attempts:
                self._sleeper(_RETRY_DELAYS[attempts])
            attempts += 1
            provider_input = ProviderAdapterInput(
                protocol=invocation.endpoint_protocol_snapshot,
                base_url=invocation.endpoint_base_url_snapshot,
                model_name=invocation.model_name_snapshot,
                admin_prompt=admin_prompt,
                input_blocks=blocks,
                max_output_tokens=invocation.max_output_tokens_snapshot,
                reasoning_effort=invocation.reasoning_effort_snapshot,
                thinking_budget_tokens=invocation.thinking_budget_tokens_snapshot,
                schema=schema,
                strategy=strategy,
                output_tool_name="structured_output",
                repair_feedback=repair_feedback,
                secret=secret,
                repair=repair_used,
            )
            attempt = start_invocation_attempt(
                invocation=invocation,
                sequence=attempts,
                phase=(
                    "PREPARE"
                    if attempts == 1
                    else ("SCHEMA_REPAIR" if repair_used else "PROVIDER_RETRY")
                ),
                strategy=strategy,
                schema=schema,
                input_bytes=sum(len(block.encode("utf-8")) for block in blocks),
                started_at=started_at,
                adapter_version=adapter_version_for_protocol(
                    invocation.endpoint_protocol_snapshot
                ),
            )
            try:
                parsed = self._invoke_provider(
                    provider_input,
                    timeout_seconds=invocation.request_timeout_seconds_snapshot,
                    max_response_bytes=self._response_limit(invocation),
                )
                if cancel_check is not None and cancel_check():
                    cancel_invocation(
                        invocation_id=invocation.id,
                        completed_at=self._clock(),
                    )
                    raise GatewayError("agents.invocation_cancelled.v1")
                if parsed.usage is None:
                    usage_trusted = False
                else:
                    usage[0] += parsed.usage.input_tokens
                    usage[1] += parsed.usage.output_tokens
                    usage[2] += parsed.usage.total_tokens
                try:
                    candidate = _validated_provider_value(
                        parsed,
                        strategy=strategy,
                        tool_name="structured_output",
                    )
                    validated_output = schema.validate_output(candidate)
                    if output_validator is not None:
                        output_validator(validated_output.value)
                except SchemaValidationError as error:
                    finish_invocation_attempt(
                        attempt=attempt,
                        phase=(
                            "SEMANTIC_REPAIR"
                            if error.code == "agents.response_semantics_invalid.v1"
                            else "SCHEMA_REPAIR"
                        ),
                        completed_at=self._completed_at(started_at),
                        safe_error_code=error.code,
                        output_bytes=parsed.response_bytes,
                        usage_trusted=parsed.usage is not None,
                        input_tokens=parsed.usage.input_tokens
                        if parsed.usage
                        else None,
                        output_tokens=parsed.usage.output_tokens
                        if parsed.usage
                        else None,
                        total_tokens=parsed.usage.total_tokens
                        if parsed.usage
                        else None,
                    )
                    last_error = GatewayError(error.code)
                    if repair_used:
                        break
                    repair_used = True
                    repair_feedback = _safe_repair_feedback(error)
                    continue
            except (ProviderTransportError, ProviderResponseError) as error:
                finish_invocation_attempt(
                    attempt=attempt,
                    phase=(
                        "INCOMPLETE"
                        if error.code == "agents.provider_incomplete.v1"
                        else "REFUSED"
                        if error.code == "agents.provider_refused.v1"
                        else "EXTRACT_REPAIR"
                        if error.code in _REPAIRABLE_PROVIDER_CODES
                        else "FAILED"
                    ),
                    completed_at=self._completed_at(started_at),
                    safe_error_code=error.code,
                )
                usage_trusted = False
                last_error = GatewayError(error.code, retryable=error.retryable)
                if error.code in _REPAIRABLE_PROVIDER_CODES and not repair_used:
                    repair_used = True
                    repair_feedback = error.code
                    continue
                if error.retryable and attempts < max_attempts:
                    continue
                break
            else:
                completed_at = self._completed_at(started_at)
                finish_invocation_attempt(
                    attempt=attempt,
                    phase="ACCEPTED",
                    completed_at=completed_at,
                    finish_reason=parsed.finish_reason,
                    output_bytes=parsed.response_bytes,
                    usage_trusted=parsed.usage is not None,
                    input_tokens=parsed.usage.input_tokens if parsed.usage else None,
                    output_tokens=parsed.usage.output_tokens if parsed.usage else None,
                    total_tokens=parsed.usage.total_tokens if parsed.usage else None,
                )
            return self._succeed(
                invocation,
                reservation,
                validated_output,
                attempts,
                usage,
                usage_trusted,
                completed_at,
            )
        finalize_invocation(
            invocation_id=invocation.id,
            reservation_id=reservation.id,
            # Failed calls do not consume the daily quota. The invocation
            # state and safe error code remain the audit/notification facts.
            actual_tokens=0,
            state=(
                AgentInvocation.State.REFUSED
                if last_error.code == "agents.provider_refused.v1"
                else AgentInvocation.State.INCOMPLETE
                if last_error.code == "agents.provider_incomplete.v1"
                else AgentInvocation.State.FAILED
            ),
            completed_at=self._completed_at(started_at),
            output_sha256="",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            safe_error_code=last_error.code,
        )
        raise last_error

    def _completed_at(self, started_at: datetime) -> datetime:
        completed_at = self._clock()
        if not timezone.is_aware(completed_at):
            raise GatewayError("agents.clock_invalid.v1")
        return max(started_at, completed_at)

    @staticmethod
    def _max_provider_attempts(invocation: AgentInvocation) -> int:
        worst_case_attempt_tokens = (
            invocation.estimated_input_tokens + invocation.max_output_tokens_snapshot
        )
        return min(
            len(_RETRY_DELAYS),
            invocation.per_run_token_limit_snapshot // worst_case_attempt_tokens,
        )

    @staticmethod
    def _response_limit(invocation: AgentInvocation) -> int:
        return min(
            MAX_PROVIDER_RESPONSE_BYTES,
            max(65_536, invocation.max_output_tokens_snapshot * 8 + 65_536),
        )

    def _succeed(
        self,
        invocation,
        reservation,
        validated_output,
        attempts,
        usage,
        trusted,
        completed_at,
    ):
        if usage[2] > reservation.requested_tokens:
            trusted = False
        settled = usage[2] if trusted else reservation.requested_tokens
        finalize_invocation(
            invocation_id=invocation.id,
            reservation_id=reservation.id,
            actual_tokens=settled,
            state=AgentInvocation.State.SUCCEEDED,
            completed_at=completed_at,
            output_sha256=_digest(validated_output.value),
            input_tokens=usage[0] if trusted else None,
            output_tokens=usage[1] if trusted else None,
            total_tokens=usage[2] if trusted else None,
            safe_error_code="",
        )
        return GatewayResult(invocation.id, validated_output, settled, attempts)


def build_agent_gateway() -> AgentGateway:
    environment = settings.AGENT_PROVIDER_ENVIRONMENT
    return AgentGateway(
        transport=default_provider_transport,
        resolver=system_provider_resolver,
        secret_registry=environment.secrets,
        internal_allowlist=environment.internal_allowlist,
    )


def invoke_structured(
    *, gateway: AgentGateway | None = None, **kwargs
) -> GatewayResult:
    runtime = gateway or build_agent_gateway()
    return runtime.execute(**kwargs)


__all__ = [
    "AgentGateway",
    "EndpointProbeInput",
    "EndpointProbeResult",
    "GatewayError",
    "GatewayResult",
    "build_agent_gateway",
    "invoke_structured",
]
