import json
from dataclasses import asdict
from datetime import date

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts.public import is_administrator
from apps.operations.public import audit_detail, search_audit


def _date(value: str) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def audit_log(request: HttpRequest) -> HttpResponse:
    actor_id = getattr(request, "account_id", None)
    admin = is_administrator(actor_id)
    if not admin:
        raise PermissionDenied
    error = ""
    try:
        rows = search_audit(
            keyword=request.GET.get("q", ""),
            action=request.GET.get("action", ""),
            target_type=request.GET.get("target_type", ""),
            target_id=request.GET.get("target_id", ""),
            start=_date(request.GET.get("start", "")),
            end=_date(request.GET.get("end", "")),
            is_admin=True,
        )
    except ValueError:
        rows = []
        error = "日期范围无效，请检查后重试。"
    detail = None
    detail_id = request.GET.get("detail", "")
    if detail_id:
        detail = audit_detail(entry_id=detail_id, is_admin=True)
        detail = {
            **asdict(detail),
            "before_json": json.dumps(
                detail.before_safe, ensure_ascii=False, sort_keys=True
            ),
            "after_json": json.dumps(
                detail.after_safe, ensure_ascii=False, sort_keys=True
            ),
        }
    return render(
        request,
        "operations/audit.html",
        {"rows": rows, "detail": detail, "error": error},
        status=422 if error else 200,
    )
