import re
import sys
from collections.abc import Callable, Mapping
from typing import Any

RuntimeErrorSink = Callable[..., object | None]

_runtime_error_sink: RuntimeErrorSink | None = None
_SAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9_.:<>()-]+")
_TRACE_CODE = re.compile(r"(?:KJ-[A-Za-z0-9-]{3,26}|trc_[0-9a-z]{26})\Z")


def configure_runtime_error_sink(sink: RuntimeErrorSink) -> None:
    global _runtime_error_sink
    _runtime_error_sink = sink


def capture_unexpected_exception(
    exception: BaseException,
    *,
    trace_code: str,
    error_code: str,
    context: Mapping[str, Any] | None = None,
) -> object | None:
    if _runtime_error_sink is not None:
        try:
            return _runtime_error_sink(
                exception,
                trace_code=trace_code,
                error_code=error_code,
                context=context,
            )
        except Exception:
            pass
    exception_type = _SAFE_IDENTIFIER.sub(
        "?", f"{type(exception).__module__}.{type(exception).__qualname__}"
    )[:192]
    safe_trace_code = trace_code if _TRACE_CODE.fullmatch(trace_code) else "-"
    try:
        sys.stderr.write(
            "runtime-error-sink-unavailable "
            f"trace={safe_trace_code} exception={exception_type}\n"
        )
    except Exception:
        pass
    return None
