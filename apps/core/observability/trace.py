import logging
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.ids import new_ulid

from .context import bind_trace_code, reset_trace_code

request_logger = logging.getLogger("kaj.requests")


def new_trace_code() -> str:
    return f"trc_{new_ulid().lower()}"


class TraceMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        trace_code = new_trace_code()
        request.trace_code = trace_code
        token = bind_trace_code(trace_code)
        try:
            response = self.get_response(request)
            response.headers["X-Trace-Code"] = trace_code
            request_logger.info(
                "Request completed method=%s status=%s",
                request.method,
                response.status_code,
                extra={"trace_code": trace_code},
            )
            return response
        finally:
            reset_trace_code(token)
