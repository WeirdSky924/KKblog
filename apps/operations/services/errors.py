import hashlib
import json
import re
import sys
import traceback
from collections.abc import Mapping
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.core.errors.redaction import DEFAULT_REDACTION_POLICY
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import Clock, SystemClock
from apps.operations.models import (
    RuntimeError as RuntimeErrorRecord,
)
from apps.operations.models import (
    RuntimeErrorOccurrence,
)

_SAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9_.:<>()-]+")
_TRACE_CODE = re.compile(r"(?:KJ-[A-Za-z0-9-]{3,26}|trc_[0-9a-z]{26})\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_.-]{2,95}\Z")
_CONTEXT_FIELDS = frozenset(
    {
        "attempt",
        "business_object",
        "method",
        "route",
        "source",
        "status",
        "task_name",
    }
)


def _identifier(value: str, *, limit: int) -> str:
    safe = _SAFE_IDENTIFIER.sub("?", value)
    return safe[:limit] or "unknown"


def _exception_type(exception: BaseException) -> str:
    exception_class = type(exception)
    return _identifier(
        f"{exception_class.__module__}.{exception_class.__qualname__}", limit=192
    )


def _trace_code(value: str) -> str:
    return value if _TRACE_CODE.fullmatch(value) else new_trace_code()


def _error_code(value: str) -> str:
    return value if _ERROR_CODE.fullmatch(value) else "core.internal_error.v1"


def _safe_context(context: Mapping[str, Any] | None) -> dict[str, object]:
    if not isinstance(context, Mapping):
        return {}
    safe: dict[str, object] = {}
    for key in sorted(set(context) & _CONTEXT_FIELDS):
        value = DEFAULT_REDACTION_POLICY.redact(context[key], key=key)
        if value is None or isinstance(value, bool | int | float):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:255]
        else:
            safe[key] = _identifier(type(value).__name__, limit=64)
    return safe


def _trace_frames(exception: BaseException) -> list[tuple[str, int, str]]:
    frames = traceback.extract_tb(exception.__traceback__, limit=40)
    return [
        (
            frame.filename,
            frame.lineno,
            _identifier(frame.name, limit=128),
        )
        for frame in frames
    ]


def _safe_traceback(exception: BaseException) -> str:
    frames = _trace_frames(exception)
    if not frames:
        return "No traceback frames were available."
    return "\n".join(
        f"[PATH]:{line_number} in {function_name}"
        for _filename, line_number, function_name in frames
    )


def _fingerprint(exception: BaseException, *, error_code: str) -> str:
    material = {
        "error_code": error_code,
        "exception": f"{type(exception).__module__}.{type(exception).__qualname__}",
        "frames": _trace_frames(exception),
    }
    encoded = json.dumps(material, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _persist_once(
    *,
    fingerprint: str,
    error_code: str,
    exception_type: str,
    safe_traceback: str,
    safe_context: dict[str, object],
    trace_code: str,
    now,
) -> RuntimeErrorRecord:
    with transaction.atomic():
        aggregate = (
            RuntimeErrorRecord.objects.select_for_update()
            .filter(fingerprint=fingerprint)
            .first()
        )
        if aggregate is None:
            aggregate = RuntimeErrorRecord.objects.create(
                fingerprint=fingerprint,
                error_code=error_code,
                exception_type=exception_type,
                safe_summary=f"Unexpected {exception_type}",
                safe_traceback=safe_traceback,
                safe_context=safe_context,
                latest_trace_code=trace_code,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
        else:
            if RuntimeErrorOccurrence.objects.filter(
                runtime_error=aggregate, trace_code=trace_code
            ).exists():
                return aggregate
            RuntimeErrorRecord.objects.filter(pk=aggregate.pk).update(
                error_code=error_code,
                exception_type=exception_type,
                safe_summary=f"Unexpected {exception_type}",
                safe_traceback=safe_traceback,
                safe_context=safe_context,
                latest_trace_code=trace_code,
                occurrence_count=F("occurrence_count") + 1,
                last_seen_at=now,
            )
        RuntimeErrorOccurrence.objects.create(
            runtime_error=aggregate,
            trace_code=trace_code,
            safe_context=safe_context,
            occurred_at=now,
        )
        aggregate.refresh_from_db()
        return aggregate


def _persist_runtime_error(
    exception: BaseException,
    *,
    trace_code: str,
    error_code: str,
    context: Mapping[str, Any] | None,
    clock: Clock | None = None,
) -> RuntimeErrorRecord:
    safe_error_code = _error_code(error_code)
    kwargs = {
        "fingerprint": _fingerprint(exception, error_code=safe_error_code),
        "error_code": safe_error_code,
        "exception_type": _exception_type(exception),
        "safe_traceback": _safe_traceback(exception),
        "safe_context": _safe_context(context),
        "trace_code": _trace_code(trace_code),
        "now": (clock or SystemClock()).now(),
    }
    for attempt in range(3):
        try:
            return _persist_once(**kwargs)
        except IntegrityError:
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def capture_runtime_error(
    exception: BaseException,
    *,
    trace_code: str,
    error_code: str = "core.internal_error.v1",
    context: Mapping[str, Any] | None = None,
    clock: Clock | None = None,
) -> RuntimeErrorRecord | None:
    safe_trace_code = _trace_code(trace_code)
    try:
        return _persist_runtime_error(
            exception,
            trace_code=safe_trace_code,
            error_code=error_code,
            context=context,
            clock=clock,
        )
    except Exception:
        diagnostic = (
            "runtime-error-persistence-failed "
            f"trace={safe_trace_code} exception={_exception_type(exception)}\n"
        )
        try:
            sys.stderr.write(diagnostic)
        except Exception:
            pass
        return None
