from contextvars import ContextVar, Token

_TRACE_CODE: ContextVar[str | None] = ContextVar("kaj_trace_code", default=None)


def current_trace_code() -> str | None:
    return _TRACE_CODE.get()


def bind_trace_code(trace_code: str) -> Token[str | None]:
    return _TRACE_CODE.set(trace_code)


def reset_trace_code(token: Token[str | None]) -> None:
    _TRACE_CODE.reset(token)
