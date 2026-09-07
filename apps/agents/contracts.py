from __future__ import annotations

from dataclasses import asdict, dataclass

DEFAULT_CONTEXT_WINDOW_TOKENS = 131_072
MIN_CONTEXT_WINDOW_TOKENS = 4_096
MAX_CONTEXT_WINDOW_TOKENS = 2_000_000

DEFAULT_MAX_OUTPUT_TOKENS = 8_192
MIN_MAX_OUTPUT_TOKENS = 256
MAX_MAX_OUTPUT_TOKENS = 131_072

DEFAULT_PER_RUN_TOKEN_LIMIT = 500_000
MIN_PER_RUN_TOKEN_LIMIT = 10_000
MAX_PER_RUN_TOKEN_LIMIT = 5_000_000

DEFAULT_REQUEST_TIMEOUT_SECONDS = 120
MIN_REQUEST_TIMEOUT_SECONDS = 10
# A structured generation request can legitimately take several minutes when
# the provider is reasoning over a large knowledge document.  The transport,
# endpoint form, and persisted endpoint constraint all share this ceiling.
MAX_REQUEST_TIMEOUT_SECONDS = 1_800

DEFAULT_CONCURRENCY_LIMIT = 1
MIN_CONCURRENCY_LIMIT = 1
MAX_CONCURRENCY_LIMIT = 5

DEFAULT_SITE_DAILY_TOKEN_LIMIT = 5_000_000
MIN_SITE_DAILY_TOKEN_LIMIT = 100_000
MAX_SITE_DAILY_TOKEN_LIMIT = 100_000_000

DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT = 2_000_000
MIN_ENDPOINT_DAILY_TOKEN_LIMIT = 50_000
MAX_ENDPOINT_DAILY_TOKEN_LIMIT = 50_000_000
MIN_THINKING_BUDGET_TOKENS = 1_024
MAX_THINKING_BUDGET_TOKENS = MAX_MAX_OUTPUT_TOKENS

DEFAULT_ENDPOINT_BASE_URLS = {
    "OPENAI_GPT": "https://api.openai.com/v1",
    "OPENAI_DEEPSEEK": "https://api.deepseek.com",
    "ANTHROPIC": "https://api.anthropic.com/v1",
}

REASONING_EFFORT_VALUES = (
    "",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


class AgentCommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _bounded_integer(value: object, *, minimum: int, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def validate_site_daily_token_limit(value: object) -> int:
    if not _bounded_integer(
        value,
        minimum=MIN_SITE_DAILY_TOKEN_LIMIT,
        maximum=MAX_SITE_DAILY_TOKEN_LIMIT,
    ):
        raise AgentCommandError(
            "agents.site_daily_limit_invalid.v1",
            "全站每日 token 上限不合法。",
        )
    return value


def default_endpoint_base_url(protocol: object) -> str:
    try:
        return DEFAULT_ENDPOINT_BASE_URLS[protocol]
    except (KeyError, TypeError):
        raise AgentCommandError(
            "agents.protocol_invalid.v1", "Endpoint 协议不合法。"
        ) from None


@dataclass(frozen=True, slots=True)
class EndpointRuntimeSettings:
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    per_run_token_limit: int = DEFAULT_PER_RUN_TOKEN_LIMIT
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS
    concurrency_limit: int = DEFAULT_CONCURRENCY_LIMIT
    endpoint_daily_token_limit: int = DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT
    reasoning_effort: str = ""
    thinking_budget_tokens: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self, *, site_daily_token_limit: object) -> EndpointRuntimeSettings:
        site_limit = validate_site_daily_token_limit(site_daily_token_limit)
        ranges = (
            (
                self.context_window_tokens,
                MIN_CONTEXT_WINDOW_TOKENS,
                MAX_CONTEXT_WINDOW_TOKENS,
            ),
            (
                self.max_output_tokens,
                MIN_MAX_OUTPUT_TOKENS,
                MAX_MAX_OUTPUT_TOKENS,
            ),
            (
                self.per_run_token_limit,
                MIN_PER_RUN_TOKEN_LIMIT,
                MAX_PER_RUN_TOKEN_LIMIT,
            ),
            (
                self.request_timeout_seconds,
                MIN_REQUEST_TIMEOUT_SECONDS,
                MAX_REQUEST_TIMEOUT_SECONDS,
            ),
            (
                self.concurrency_limit,
                MIN_CONCURRENCY_LIMIT,
                MAX_CONCURRENCY_LIMIT,
            ),
            (
                self.endpoint_daily_token_limit,
                MIN_ENDPOINT_DAILY_TOKEN_LIMIT,
                MAX_ENDPOINT_DAILY_TOKEN_LIMIT,
            ),
        )
        if self.reasoning_effort not in REASONING_EFFORT_VALUES:
            raise AgentCommandError(
                "agents.reasoning_effort_invalid.v1", "推理强度参数不合法。"
            )
        if self.thinking_budget_tokens is not None and (
            isinstance(self.thinking_budget_tokens, bool)
            or not MIN_THINKING_BUDGET_TOKENS
            <= self.thinking_budget_tokens
            <= MAX_THINKING_BUDGET_TOKENS
            or self.thinking_budget_tokens >= self.max_output_tokens
        ):
            raise AgentCommandError(
                "agents.thinking_budget_invalid.v1", "思考 token 预算不合法。"
            )
        if any(
            not _bounded_integer(value, minimum=minimum, maximum=maximum)
            for value, minimum, maximum in ranges
        ) or not (
            self.max_output_tokens < self.context_window_tokens
            and self.per_run_token_limit >= self.max_output_tokens
            and self.per_run_token_limit <= self.endpoint_daily_token_limit
            and self.endpoint_daily_token_limit <= site_limit
        ):
            raise AgentCommandError(
                "agents.runtime_limits_invalid.v1",
                "Endpoint 运行参数超出允许范围或互相冲突。",
            )
        return self

    def validate_input_estimate(self, estimated_input_tokens: object) -> int:
        if (
            not _bounded_integer(
                estimated_input_tokens,
                minimum=0,
                maximum=MAX_PER_RUN_TOKEN_LIMIT,
            )
            or (
                estimated_input_tokens + self.max_output_tokens
                > self.context_window_tokens
            )
            or (
                estimated_input_tokens + self.max_output_tokens
                > self.per_run_token_limit
            )
        ):
            raise AgentCommandError(
                "agents.input_budget_exceeded.v1",
                "输入与输出预算超过 Endpoint 上下文或单次业务上限。",
            )
        return estimated_input_tokens


__all__ = [
    "AgentCommandError",
    "DEFAULT_CONCURRENCY_LIMIT",
    "DEFAULT_CONTEXT_WINDOW_TOKENS",
    "DEFAULT_ENDPOINT_DAILY_TOKEN_LIMIT",
    "DEFAULT_ENDPOINT_BASE_URLS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_PER_RUN_TOKEN_LIMIT",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_SITE_DAILY_TOKEN_LIMIT",
    "MAX_THINKING_BUDGET_TOKENS",
    "MIN_THINKING_BUDGET_TOKENS",
    "EndpointRuntimeSettings",
    "REASONING_EFFORT_VALUES",
    "default_endpoint_base_url",
    "validate_site_daily_token_limit",
]
