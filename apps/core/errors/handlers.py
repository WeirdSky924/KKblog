import logging

from django.core.exceptions import BadRequest, PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin

from apps.core.http import HTMX_VARIANT_HEADERS, is_htmx_fragment_request
from apps.core.observability.context import current_trace_code
from apps.core.observability.trace import new_trace_code

from .codes import ErrorCode, ErrorSpec, spec_for
from .exceptions import DomainError
from .runtime_sink import capture_unexpected_exception

logger = logging.getLogger("kaj.errors")

_ERROR_TITLES = {
    401: "请先登录",
    403: "暂时无法访问此页面",
    404: "页面没有找到",
    409: "内容已经发生变化",
    422: "暂时无法完成操作",
    429: "操作过于频繁",
    500: "页面暂时无法显示",
    503: "服务暂时不可用",
}


def _request_trace(request: HttpRequest) -> str:
    trace_code = getattr(request, "trace_code", None) or current_trace_code()
    if trace_code:
        return trace_code
    trace_code = new_trace_code()
    request.trace_code = trace_code
    return trace_code


def render_error_response(
    request: HttpRequest,
    spec: ErrorSpec,
    *,
    retry_after: int | None = None,
) -> HttpResponse:
    trace_code = _request_trace(request)
    request.kaj_error_shell = True
    template = (
        "errors/partial.html"
        if is_htmx_fragment_request(request)
        else "errors/page.html"
    )
    response = render(
        request,
        template,
        {
            "status": spec.status,
            "error_title": _ERROR_TITLES[spec.status],
            "safe_message": spec.message,
            "trace_code": trace_code,
            "retryable": spec.status >= 500,
        },
        status=spec.status,
    )
    response.headers["X-Trace-Code"] = trace_code
    response.headers["Cache-Control"] = "no-store"
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    patch_vary_headers(response, HTMX_VARIANT_HEADERS)
    return response


class ErrorResponseMiddleware(MiddlewareMixin):
    def process_exception(
        self, request: HttpRequest, exception: BaseException
    ) -> HttpResponse:
        if isinstance(exception, DomainError):
            return render_error_response(
                request,
                spec_for(exception.code),
                retry_after=exception.retry_after,
            )
        if isinstance(exception, Http404):
            return render_error_response(request, spec_for(ErrorCode.NOT_FOUND))
        if isinstance(exception, PermissionDenied):
            return render_error_response(request, spec_for(ErrorCode.PERMISSION_DENIED))
        if isinstance(exception, (BadRequest, ValidationError)):
            return render_error_response(request, spec_for(ErrorCode.VALIDATION_FAILED))

        trace_code = _request_trace(request)
        resolver_match = getattr(request, "resolver_match", None)
        capture_unexpected_exception(
            exception,
            trace_code=trace_code,
            error_code=ErrorCode.INTERNAL_ERROR.value,
            context={
                "method": request.method,
                "route": getattr(resolver_match, "view_name", "") or "unresolved",
                "source": "http",
            },
        )
        logger.error("Unhandled request exception", extra={"trace_code": trace_code})
        return render_error_response(request, spec_for(ErrorCode.INTERNAL_ERROR))


def permission_denied(
    request: HttpRequest, exception: BaseException | None = None
) -> HttpResponse:
    del exception
    return render_error_response(request, spec_for(ErrorCode.PERMISSION_DENIED))


def not_found(
    request: HttpRequest, exception: BaseException | None = None
) -> HttpResponse:
    del exception
    return render_error_response(request, spec_for(ErrorCode.NOT_FOUND))


def server_error(request: HttpRequest) -> HttpResponse:
    logger.error(
        "Unhandled request reached the server error handler",
        extra={"trace_code": _request_trace(request)},
    )
    return render_error_response(request, spec_for(ErrorCode.INTERNAL_ERROR))
