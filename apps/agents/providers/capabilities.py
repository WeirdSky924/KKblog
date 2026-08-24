"""Provider/model reasoning capability resolution.

Reasoning controls are not a universal OpenAI-compatible contract.  Keep the
small, reviewed capability registry here so forms, configuration validation and
provider adapters make the same decision for a given model snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.agents.contracts import (
    MAX_THINKING_BUDGET_TOKENS,
    MIN_THINKING_BUDGET_TOKENS,
    REASONING_EFFORT_VALUES,
    AgentCommandError,
)
from apps.agents.models import AgentEndpoint


@dataclass(frozen=True, slots=True)
class ReasoningCapability:
    family: str
    transport: str
    effort_levels: tuple[str, ...] = ()
    supports_thinking_budget: bool = False
    supports_adaptive_thinking: bool = False

    @property
    def supports_effort(self) -> bool:
        return bool(self.effort_levels)


_OPENAI_REASONING = ReasoningCapability(
    family="openai-reasoning",
    transport="openai",
    effort_levels=("low", "medium", "high"),
)
_OPENAI_GPT5 = ReasoningCapability(
    family="openai-gpt5",
    transport="openai",
    effort_levels=("none", "minimal", "low", "medium", "high", "xhigh", "max"),
)
_DEEPSEEK_V4 = ReasoningCapability(
    family="deepseek-v4",
    transport="deepseek",
    effort_levels=("low", "high", "max"),
)
_ANTHROPIC_EFFORT = ReasoningCapability(
    family="anthropic-adaptive",
    transport="anthropic-effort",
    effort_levels=("low", "medium", "high", "xhigh", "max"),
    supports_adaptive_thinking=True,
)
_ANTHROPIC_BUDGET = ReasoningCapability(
    family="anthropic-budget",
    transport="anthropic-budget",
    supports_thinking_budget=True,
)
_UNSUPPORTED = ReasoningCapability(family="unsupported", transport="none")


def resolve_reasoning_capability(protocol: str, model_name: str) -> ReasoningCapability:
    """Resolve a conservative capability profile from protocol and model ID.

    Unknown custom OpenAI-compatible models intentionally resolve to no
    reasoning controls.  An administrator must not accidentally send a
    provider-specific parameter to an endpoint that has not advertised it.
    """
    model = model_name.strip().casefold() if isinstance(model_name, str) else ""
    if protocol == AgentEndpoint.Protocol.OPENAI_DEEPSEEK:
        if "deepseek-v4" in model:
            return _DEEPSEEK_V4
        return _UNSUPPORTED
    if protocol == AgentEndpoint.Protocol.OPENAI_GPT:
        if model.startswith("gpt-5"):
            return _OPENAI_GPT5
        if model.startswith(("o1", "o3", "o4")):
            return _OPENAI_REASONING
        return _UNSUPPORTED
    if protocol == AgentEndpoint.Protocol.ANTHROPIC:
        if any(
            marker in model
            for marker in (
                "claude-opus-4-6",
                "claude-opus-4-7",
                "claude-sonnet-4-6",
                "claude-sonnet-4-7",
                "claude-opus-5",
                "claude-sonnet-5",
            )
        ):
            return _ANTHROPIC_EFFORT
        if any(marker in model for marker in ("claude-3-7", "claude-4-")):
            return _ANTHROPIC_BUDGET
    return _UNSUPPORTED


def reasoning_effort_choices(
    protocol: str, model_name: str
) -> tuple[tuple[str, str], ...]:
    capability = resolve_reasoning_capability(protocol, model_name)
    labels = {
        "none": "关闭推理",
        "minimal": "最小",
        "low": "低",
        "medium": "中",
        "high": "高",
        "xhigh": "极高",
        "max": "最大",
    }
    return (("", "不设置（使用上游默认值）"),) + tuple(
        (value, labels[value]) for value in capability.effort_levels
    )


def validate_reasoning_settings(
    *,
    protocol: str,
    model_name: str,
    reasoning_effort: str,
    thinking_budget_tokens: int | None,
    max_output_tokens: int,
) -> None:
    capability = resolve_reasoning_capability(protocol, model_name)
    if reasoning_effort not in REASONING_EFFORT_VALUES:
        raise AgentCommandError(
            "agents.reasoning_effort_invalid.v1", "推理强度参数不合法。"
        )
    if reasoning_effort and reasoning_effort not in capability.effort_levels:
        raise AgentCommandError(
            "agents.reasoning_effort_unsupported.v1",
            "当前模型不支持所选推理强度。",
        )
    if thinking_budget_tokens is not None:
        if (
            not capability.supports_thinking_budget
            or isinstance(thinking_budget_tokens, bool)
            or not MIN_THINKING_BUDGET_TOKENS
            <= thinking_budget_tokens
            <= MAX_THINKING_BUDGET_TOKENS
            or thinking_budget_tokens >= max_output_tokens
        ):
            raise AgentCommandError(
                "agents.thinking_budget_invalid.v1",
                "当前模型不支持该思考预算，或思考预算必须小于单次输出上限。",
            )
    if reasoning_effort and thinking_budget_tokens is not None:
        raise AgentCommandError(
            "agents.reasoning_configuration_conflict.v1",
            "推理强度和思考 token 预算不能同时设置。",
        )


__all__ = [
    "ReasoningCapability",
    "reasoning_effort_choices",
    "resolve_reasoning_capability",
    "validate_reasoning_settings",
]
