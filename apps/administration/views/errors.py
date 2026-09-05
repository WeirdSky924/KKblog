from datetime import date

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts.public import is_administrator
from apps.operations.public import error_detail, search_runtime_errors


def _date(value: str) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def runtime_errors(request: HttpRequest) -> HttpResponse:
    actor_id = getattr(request, "account_id", None)
    if not is_administrator(actor_id):
        raise PermissionDenied

    trace_code = request.GET.get("trace", "").strip()
    error = ""
    try:
        page_number = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page_number = 1
        error = "分页条件无效，请检查后重试。"
    try:
        error_page = search_runtime_errors(
            trace_code=trace_code,
            error_code=request.GET.get("error_code", ""),
            keyword=request.GET.get("q", ""),
            start=_date(request.GET.get("start", "")),
            end=_date(request.GET.get("end", "")),
            is_admin=True,
            page=page_number,
            page_size=20,
        )
    except ValueError:
        error_page = search_runtime_errors(is_admin=True, page=1, page_size=20)
        error = "日期范围无效，请检查后重试。"

    detail = None
    detail_missing = False
    detail_id = request.GET.get("detail", "").strip()
    if detail_id and not error:
        detail = error_detail(error_id=detail_id, is_admin=True)
        detail_missing = detail is None

    return render(
        request,
        "operations/errors.html",
        {
            "rows": error_page.items,
            "error_page": error_page,
            "pagination_query": _pagination_query(request),
            "detail": detail,
            "detail_missing": detail_missing,
            "error": error,
            "trace_query": trace_code,
        },
        status=422 if error else 200,
    )


def _pagination_query(request):
    values = request.GET.copy()
    values.pop("page", None)
    return values.urlencode()
