from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .http import ProviderHttpRequest, ProviderHttpResponse


class DeterministicFakeProviderTransport:
    def __init__(
        self,
        *,
        value: Mapping[str, object],
        input_tokens: int = 10,
        output_tokens: int = 5,
        include_usage: bool = True,
    ) -> None:
        self._value = dict(value)
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._include_usage = include_usage
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def __repr__(self) -> str:
        return f"{type(self).__name__}(call_count={self._call_count})"

    def __call__(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        self._call_count += 1
        value = json.dumps(self._value, ensure_ascii=False, separators=(",", ":"))
        request_payload = json.loads(request.body.decode("utf-8"))
        tool_requested = bool(request_payload.get("tools"))
        tool_name = "structured_output"
        if tool_requested:
            first_tool = request_payload["tools"][0]
            if "function" in first_tool:
                tool_name = first_tool["function"]["name"]
            else:
                tool_name = first_tool["name"]
        if "anthropic-version" in {key.casefold() for key in request.headers}:
            payload: dict[str, object] = {
                "content": [
                    {"type": "tool_use", "name": tool_name, "input": self._value}
                    if tool_requested
                    else {"type": "text", "text": value}
                ]
            }
            if self._include_usage:
                payload["usage"] = {
                    "input_tokens": self._input_tokens,
                    "output_tokens": self._output_tokens,
                }
        else:
            payload = {
                "choices": [
                    {
                        "message": (
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": value,
                                        },
                                    }
                                ]
                            }
                            if tool_requested
                            else {"role": "assistant", "content": value}
                        )
                    }
                ]
            }
            if self._include_usage:
                payload["usage"] = {
                    "prompt_tokens": self._input_tokens,
                    "completion_tokens": self._output_tokens,
                    "total_tokens": self._input_tokens + self._output_tokens,
                }
        return ProviderHttpResponse(
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )


class ScriptedProviderTransport:
    def __init__(self, script: Sequence[object]) -> None:
        self._script = list(script)
        self._call_count = 0
        self._last_request: ProviderHttpRequest | None = None

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def last_request(self) -> ProviderHttpRequest | None:
        return self._last_request

    def __repr__(self) -> str:
        return f"{type(self).__name__}(call_count={self._call_count})"

    def __call__(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        self._call_count += 1
        self._last_request = request
        if not self._script:
            raise RuntimeError("Script exhausted")
        outcome = self._script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome = outcome(request)
        if not isinstance(outcome, ProviderHttpResponse):
            raise TypeError("Invalid scripted provider response")
        return outcome


__all__ = ["DeterministicFakeProviderTransport", "ScriptedProviderTransport"]
