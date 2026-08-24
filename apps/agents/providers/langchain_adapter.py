"""LangChain-backed structured provider invocation.

LangChain owns provider-specific message/schema binding here.  The Gateway still
owns retries, token reservations, leases, and the project's final validation.
Network requests are routed through ``SafeProviderHttpClient`` so LangChain
cannot bypass endpoint policy or secret handling.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from apps.agents.models import AgentEndpoint
from apps.agents.providers.capabilities import resolve_reasoning_capability
from apps.agents.schemas import decode_json_object

from .adapters import (
    ParsedProviderResponse,
    ProviderAdapterInput,
    ProviderResponseError,
    ProviderToolCall,
    ProviderUsage,
    _material,
    _openai_base_url,
    _system,
)
from .http import (
    MAX_PROVIDER_RESPONSE_BYTES,
    ProviderTransportError,
    SafeProviderHttpClient,
)

try:  # Optional at import time so existing local test environments fail clearly.
    import httpx
    from langchain_anthropic import ChatAnthropic
    from langchain_anthropic import __version__ as _ANTHROPIC_VERSION
    from langchain_openai import ChatOpenAI
    from langchain_openai import __version__ as _OPENAI_VERSION

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by dependency smoke tests
    httpx = None  # type: ignore[assignment]
    ChatAnthropic = None  # type: ignore[assignment,misc]
    ChatOpenAI = None  # type: ignore[assignment,misc]
    _ANTHROPIC_VERSION = ""
    _OPENAI_VERSION = ""
    LANGCHAIN_AVAILABLE = False


_ALLOWED_HEADERS = frozenset(
    {
        "accept",
        "anthropic-beta",
        "anthropic-version",
        "authorization",
        "content-type",
        "x-api-key",
    }
)
_AUTH_HEADERS = frozenset({"authorization", "x-api-key"})
_CANONICAL_HEADERS = {
    "accept": "Accept",
    "anthropic-beta": "anthropic-beta",
    "anthropic-version": "anthropic-version",
    "authorization": "Authorization",
    "content-type": "Content-Type",
    "x-api-key": "x-api-key",
}
_OPENAI_GENERATION_UNSUPPORTED_KEYS = frozenset(
    {
        "maxItems",
        "maxLength",
        "minItems",
        "minLength",
        "minimum",
        "maximum",
        "pattern",
        "uniqueItems",
    }
)
_GPT5_MODEL = re.compile(r"^(?:o[134](?:-|$)|gpt-5(?:-|$))", re.IGNORECASE)


class LangChainUnavailable(ProviderResponseError):
    def __init__(self) -> None:
        super().__init__("agents.langchain_unavailable.v1")


class _SafeHttpxTransport(httpx.BaseTransport if httpx else object):
    """Adapt LangChain's httpx/OpenAI clients to the existing safe client."""

    def __init__(
        self,
        client: SafeProviderHttpClient,
        *,
        timeout_seconds: int,
        max_response_bytes: int,
        allow_auth_headers: bool,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._allow_auth_headers = allow_auth_headers

    def handle_request(self, request):  # type: ignore[no-untyped-def]
        try:
            payload = json.loads(request.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderTransportError("agents.provider_request_invalid.v1") from None
        if not isinstance(payload, Mapping):
            raise ProviderTransportError("agents.provider_request_invalid.v1")
        headers = {}
        for name, value in request.headers.multi_items():
            normalized = name.casefold()
            if normalized not in _ALLOWED_HEADERS:
                continue
            if not self._allow_auth_headers and normalized in _AUTH_HEADERS:
                continue
            headers[_CANONICAL_HEADERS[normalized]] = value
        response = self._client.post_json(
            str(request.url),
            payload,
            headers=headers,
            timeout_seconds=self._timeout_seconds,
            max_response_bytes=self._max_response_bytes,
            max_redirects=1,
        )
        return httpx.Response(
            response.status,
            headers=dict(response.headers),
            content=response.body,
            request=request,
        )


@dataclass(frozen=True, slots=True)
class _ClientContext(AbstractContextManager):
    client: Any

    def __enter__(self):
        return self.client

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.close()
        return False


def _httpx_client(
    safe_client: SafeProviderHttpClient,
    *,
    timeout_seconds: int,
    max_response_bytes: int,
    allow_auth_headers: bool,
) -> _ClientContext:
    if not LANGCHAIN_AVAILABLE:
        raise LangChainUnavailable()
    return _ClientContext(
        httpx.Client(
            transport=_SafeHttpxTransport(
                safe_client,
                timeout_seconds=timeout_seconds,
                max_response_bytes=max_response_bytes,
                allow_auth_headers=allow_auth_headers,
            ),
            timeout=timeout_seconds,
        )
    )


def _usage(raw: object) -> ProviderUsage | None:
    values = None
    if raw is not None:
        metadata = getattr(raw, "usage_metadata", None)
        if isinstance(metadata, Mapping):
            values = (
                metadata.get("input_tokens"),
                metadata.get("output_tokens"),
                metadata.get("total_tokens"),
            )
        if values is None:
            metadata = getattr(raw, "response_metadata", None)
            token_usage = (
                metadata.get("token_usage") if isinstance(metadata, Mapping) else None
            )
            if isinstance(token_usage, Mapping):
                values = (
                    token_usage.get("prompt_tokens"),
                    token_usage.get("completion_tokens"),
                    token_usage.get("total_tokens"),
                )
    if values is None:
        return None
    input_tokens, output_tokens, total_tokens = values
    if (
        any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in values
        )
        or input_tokens + output_tokens != total_tokens
    ):
        return None
    return ProviderUsage(input_tokens, output_tokens, total_tokens)


def _tool_calls(raw: object) -> tuple[ProviderToolCall, ...]:
    # Prefer the provider's raw additional kwargs: OpenAI-compatible messages
    # keep tool arguments as JSON text there, which lets our duplicate-key
    # decoder run before LangChain turns them into a plain dict.
    additional = getattr(raw, "additional_kwargs", None)
    calls = additional.get("tool_calls") if isinstance(additional, Mapping) else None
    if not isinstance(calls, list):
        calls = getattr(raw, "tool_calls", None)
    if not isinstance(calls, list):
        return ()
    result = []
    for call in calls:
        if not isinstance(call, Mapping):
            raise ProviderResponseError("agents.response_invalid.v1")
        function = (
            call.get("function") if isinstance(call.get("function"), Mapping) else call
        )
        name = function.get("name")
        arguments = function.get(
            "args", function.get("arguments", function.get("input"))
        )
        if not isinstance(name, str):
            raise ProviderResponseError("agents.response_invalid.v1")
        if isinstance(arguments, str):
            try:
                arguments = decode_json_object(arguments)
            except Exception as error:
                raise ProviderResponseError(
                    getattr(error, "code", "agents.response_invalid.v1")
                ) from None
        if not isinstance(arguments, Mapping):
            raise ProviderResponseError("agents.response_invalid.v1")
        result.append(ProviderToolCall(name, dict(arguments)))
    return tuple(result)


def _message_content(raw: object) -> tuple[str, ...]:
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return ("text",) if content else ()
    if isinstance(content, list):
        blocks = []
        for block in content:
            if isinstance(block, Mapping) and isinstance(block.get("type"), str):
                blocks.append(block["type"])
        return tuple(blocks)
    return ()


def _raw_json_value(raw: object) -> Mapping[str, object] | None:
    content = getattr(raw, "content", None)
    if isinstance(content, str) and content.strip():
        return decode_json_object(content)
    if isinstance(content, list):
        texts = [
            block.get("text")
            for block in content
            if isinstance(block, Mapping) and block.get("type") == "text"
        ]
        if len(texts) == 1 and isinstance(texts[0], str) and texts[0].strip():
            return decode_json_object(texts[0])
    return None


def _map_exception(error: BaseException) -> ProviderResponseError:
    if isinstance(error, ProviderResponseError):
        return error
    if isinstance(error, ProviderTransportError):
        return ProviderResponseError(error.code, retryable=error.retryable)
    cause = error.__cause__
    if isinstance(cause, ProviderTransportError):
        return ProviderResponseError(cause.code, retryable=cause.retryable)
    response = getattr(error, "response", None)
    status = getattr(error, "status_code", None) or getattr(
        response, "status_code", None
    )
    if isinstance(status, int):
        if status in {408, 409, 425, 429} or status >= 500:
            return ProviderResponseError("agents.provider_transient.v1", retryable=True)
        if status in {401, 403}:
            return ProviderResponseError("agents.provider_auth_failed.v1")
        if status in {400, 422}:
            return ProviderResponseError("agents.provider_request_invalid.v1")
        if status == 404:
            return ProviderResponseError("agents.provider_endpoint_not_found.v1")
    if isinstance(error, (TimeoutError, OSError)) or type(error).__name__ in {
        "APIConnectionError",
        "ConnectError",
        "ReadTimeout",
        "TimeoutException",
    }:
        return ProviderResponseError("agents.request_network_failed.v1", retryable=True)
    if type(error).__name__ == "LengthFinishReasonError":
        return ProviderResponseError("agents.provider_incomplete.v1")
    return ProviderResponseError("agents.response_invalid.v1")


def _terminal_response_error(raw: object) -> ProviderResponseError | None:
    additional = getattr(raw, "additional_kwargs", None)
    if isinstance(additional, Mapping) and additional.get("refusal"):
        return ProviderResponseError("agents.provider_refused.v1")
    metadata = getattr(raw, "response_metadata", None)
    finish_reason = (
        metadata.get("finish_reason") if isinstance(metadata, Mapping) else None
    )
    if finish_reason in {"length", "max_tokens"}:
        return ProviderResponseError("agents.provider_incomplete.v1")
    return None


def _model_and_method(
    input: ProviderAdapterInput,
    http_client: Any,
    *,
    timeout_seconds: int,
):
    api_key = input.secret or "kajspace-no-auth"
    if input.protocol in {
        AgentEndpoint.Protocol.OPENAI_GPT,
        AgentEndpoint.Protocol.OPENAI_DEEPSEEK,
    }:
        kwargs = {
            "model": input.model_name,
            "api_key": api_key,
            "base_url": _openai_base_url(input.base_url),
            "max_retries": 0,
            "http_client": http_client,
            "max_completion_tokens": input.max_output_tokens,
        }
        if not _GPT5_MODEL.match(input.model_name):
            if not input.reasoning_effort:
                kwargs["temperature"] = 0
        if input.reasoning_effort:
            kwargs["reasoning_effort"] = input.reasoning_effort
            if input.protocol == AgentEndpoint.Protocol.OPENAI_DEEPSEEK:
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        model = ChatOpenAI(**kwargs)
        method = {
            "native": "json_schema",
            "tool": "function_calling",
            "json_best_effort": "json_mode",
        }.get(input.strategy, "json_schema")
        return model, method
    if input.protocol == AgentEndpoint.Protocol.ANTHROPIC:
        # ChatAnthropic does not expose http_client as a public model field in
        # this release. Its cached SDK client is replaced before invocation;
        # no default client is ever created or allowed to make a request.
        anthropic_kwargs = {
            "model": input.model_name,
            "api_key": api_key,
            "base_url": input.base_url,
            "max_tokens": input.max_output_tokens,
            "max_retries": 0,
            "timeout": timeout_seconds,
        }
        capability = resolve_reasoning_capability(
            AgentEndpoint.Protocol.ANTHROPIC, input.model_name
        )
        if input.thinking_budget_tokens is not None:
            anthropic_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": input.thinking_budget_tokens,
            }
        elif input.reasoning_effort:
            anthropic_kwargs["reasoning_effort"] = input.reasoning_effort
            if capability.supports_adaptive_thinking:
                anthropic_kwargs["thinking"] = {
                    "type": "adaptive",
                    "display": "summarized",
                }
        model = ChatAnthropic(
            **anthropic_kwargs,
        )
        import anthropic

        model.__dict__["_client"] = anthropic.Client(
            api_key=api_key,
            base_url=input.base_url,
            max_retries=0,
            http_client=http_client,
        )
        return model, (
            "function_calling" if input.strategy == "tool" else "json_schema"
        )
    raise ProviderResponseError("agents.protocol_invalid.v1")


def _adapter_version(protocol: str) -> str:
    if protocol == AgentEndpoint.Protocol.ANTHROPIC:
        return (
            f"langchain-anthropic-{_ANTHROPIC_VERSION}"
            if _ANTHROPIC_VERSION
            else "langchain-anthropic-unavailable"
        )[:32]
    return (
        f"langchain-openai-{_OPENAI_VERSION}"
        if _OPENAI_VERSION
        else "langchain-openai-unavailable"
    )[:32]


def adapter_version_for_protocol(protocol: str) -> str:
    return _adapter_version(protocol)


def _provider_schema(schema: Mapping[str, object], *, protocol: str):
    """Project local validation constraints to a provider generation schema.

    The local SchemaSpec remains authoritative. OpenAI-compatible strict
    generation accepts only a subset of JSON Schema keywords; length, pattern,
    uniqueness, and numeric bounds are enforced after extraction instead.
    """
    if protocol not in {
        AgentEndpoint.Protocol.OPENAI_GPT,
        AgentEndpoint.Protocol.OPENAI_DEEPSEEK,
    }:
        return dict(schema)

    def project(value):
        if isinstance(value, Mapping):
            return {
                key: project(child)
                for key, child in value.items()
                if key not in _OPENAI_GENERATION_UNSUPPORTED_KEYS
            }
        if isinstance(value, list):
            return [project(child) for child in value]
        return value

    return project(schema)


def probe_langchain_connectivity(
    input: ProviderAdapterInput,
    *,
    safe_client: SafeProviderHttpClient,
    timeout_seconds: int,
    max_response_bytes: int = 65_536,
) -> ParsedProviderResponse:
    """Call the configured model without schema or tool constraints."""
    if not LANGCHAIN_AVAILABLE:
        raise LangChainUnavailable()
    with _httpx_client(
        safe_client,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        allow_auth_headers=bool(input.secret),
    ) as http_client:
        try:
            model, _ = _model_and_method(
                input,
                http_client,
                timeout_seconds=timeout_seconds,
            )
            raw = model.invoke(
                [
                    (
                        "system",
                        "This is an administrator-requested connectivity check. "
                        "Do not call tools. Return a short acknowledgement.",
                    ),
                    ("human", "Reply with OK."),
                ]
            )
        except Exception as error:
            raise _map_exception(error) from None
    terminal_error = _terminal_response_error(raw)
    if terminal_error is not None:
        raise terminal_error
    calls = _tool_calls(raw)
    content_blocks = _message_content(raw)
    content = getattr(raw, "content", None)
    if calls or not content_blocks or content is None or content == "":
        raise ProviderResponseError("agents.response_invalid.v1")
    try:
        response_bytes = len(
            json.dumps(content, ensure_ascii=False, default=str).encode("utf-8")
        )
    except (TypeError, ValueError):
        raise ProviderResponseError("agents.response_invalid.v1") from None
    metadata = getattr(raw, "response_metadata", None)
    finish_reason = (
        str(metadata.get("finish_reason") or "")
        if isinstance(metadata, Mapping)
        else ""
    )
    return ParsedProviderResponse(
        value={"ok": True},
        usage=_usage(raw),
        finish_reason=finish_reason,
        content_blocks=content_blocks,
        response_bytes=response_bytes,
        adapter_version=_adapter_version(input.protocol),
    )


def invoke_langchain(
    input: ProviderAdapterInput,
    *,
    safe_client: SafeProviderHttpClient,
    timeout_seconds: int,
    max_response_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
) -> ParsedProviderResponse:
    if not LANGCHAIN_AVAILABLE:
        raise LangChainUnavailable()
    with _httpx_client(
        safe_client,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        allow_auth_headers=bool(input.secret),
    ) as http_client:
        try:
            model, method = _model_and_method(
                input,
                http_client,
                timeout_seconds=timeout_seconds,
            )
            if method == "function_calling":
                structure = {
                    "name": input.output_tool_name,
                    "description": "Return the validated structured result.",
                    "input_schema": _provider_schema(
                        input.schema.provider_schema,
                        protocol=input.protocol,
                    ),
                }
            elif input.protocol == AgentEndpoint.Protocol.OPENAI_GPT:
                structure = {
                    "name": input.output_tool_name,
                    "description": "Return the validated structured result.",
                    "schema": _provider_schema(
                        input.schema.provider_schema,
                        protocol=input.protocol,
                    ),
                }
            else:
                structure = dict(input.schema.provider_schema)
            structured = model.with_structured_output(
                structure,
                method=method,
                include_raw=True,
                strict=True if method != "json_mode" else None,
            )
            result = structured.invoke(
                [
                    ("system", _system(input)),
                    ("human", _material(input.input_blocks)),
                ]
            )
        except Exception as error:
            mapped = _map_exception(error)
            raise mapped from None
    if not isinstance(result, Mapping):
        raise ProviderResponseError("agents.response_invalid.v1")
    raw = result.get("raw")
    terminal_error = _terminal_response_error(raw)
    if terminal_error is not None:
        raise terminal_error
    parsing_error = result.get("parsing_error")
    if parsing_error is not None:
        raise _map_exception(parsing_error)
    calls = _tool_calls(raw)
    parsed = result.get("parsed")
    if not calls:
        try:
            raw_value = _raw_json_value(raw)
        except Exception as error:
            raise ProviderResponseError(
                getattr(error, "code", "agents.response_invalid.v1")
            ) from None
        if raw_value is not None:
            parsed = raw_value
    if hasattr(parsed, "model_dump"):
        parsed = parsed.model_dump()
    if not isinstance(parsed, Mapping):
        raise ProviderResponseError("agents.response_invalid.v1")
    content_blocks = _message_content(raw)
    return ParsedProviderResponse(
        value=dict(parsed),
        usage=_usage(raw),
        finish_reason=str(
            getattr(raw, "response_metadata", {}).get("finish_reason", "")
            if isinstance(getattr(raw, "response_metadata", None), Mapping)
            else ""
        ),
        content_blocks=content_blocks or (("tool_use",) if calls else ("text",)),
        tool_calls=calls,
        response_bytes=len(
            json.dumps(dict(parsed), ensure_ascii=False).encode("utf-8")
        ),
        adapter_version=_adapter_version(input.protocol),
    )


__all__ = [
    "LANGCHAIN_AVAILABLE",
    "LangChainUnavailable",
    "adapter_version_for_protocol",
    "invoke_langchain",
    "probe_langchain_connectivity",
]
