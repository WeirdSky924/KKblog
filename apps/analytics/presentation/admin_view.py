from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.analytics.services.access import (
    can_access_dashboard,
    is_dashboard_proxy_path,
)

_PRIVATE_NO_STORE = "private, no-store"


def _not_found() -> HttpResponse:
    response = HttpResponse(status=404)
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE
    return response


@require_GET
def analytics_dashboard(request: HttpRequest) -> HttpResponse:
    if not can_access_dashboard(getattr(request, "account_id", None)):
        raise PermissionDenied
    enabled = bool(
        getattr(settings, "ANALYTICS_ENABLED", False)
        and getattr(settings, "ANALYTICS_WEBSITE_ID", "")
    )
    response = render(
        request,
        "analytics/dashboard.html",
        {"analytics_enabled": enabled},
        status=200 if enabled else 503,
    )
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE
    return response


@require_GET
def internal_authorize(request: HttpRequest) -> HttpResponse:
    if (
        request.headers.get("X-Kaj-Internal-Auth") != "1"
        or not getattr(settings, "ANALYTICS_ENABLED", False)
        or not is_dashboard_proxy_path(request.headers.get("X-Forwarded-Uri", ""))
        or not can_access_dashboard(getattr(request, "account_id", None))
    ):
        return _not_found()
    response = HttpResponse(status=204)
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE
    return response
