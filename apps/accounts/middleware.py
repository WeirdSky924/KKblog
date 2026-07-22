from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.accounts.models import IpBlock, LoginSession
from apps.accounts.models.session import session_token_digest
from apps.accounts.network import resolve_client_ip
from apps.core.errors import ErrorCode, spec_for
from apps.core.errors.handlers import render_error_response


def _resolve_product_route(request: HttpRequest):
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return None
    if not match.namespace:
        return None
    exempt = frozenset(
        getattr(
            settings,
            "NETWORK_POLICY_EXEMPT_VIEW_NAMES",
            ("operations:live", "operations:ready"),
        )
    )
    return None if match.view_name in exempt else match


def _public_browse(request: HttpRequest, match) -> bool:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return False
    namespaces = frozenset(
        getattr(settings, "NETWORK_PUBLIC_NAMESPACES", ("public", "article"))
    )
    return match.namespace in namespaces


class NetworkPolicyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.client_ip = resolve_client_ip(request)
        match = _resolve_product_route(request)
        if match is None:
            request.network_blocked = False
            request.force_guest = False
            return self.get_response(request)
        request.network_blocked = IpBlock.objects.filter(
            address=request.client_ip,
            unblocked_at__isnull=True,
        ).exists()
        request.force_guest = request.network_blocked and _public_browse(request, match)
        if request.network_blocked and not request.force_guest:
            return render_error_response(
                request, spec_for(ErrorCode.NETWORK_RESTRICTED)
            )
        return self.get_response(request)


class AccountSessionMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.account_id = None
        request.account = None
        request.login_session = None
        if getattr(request, "force_guest", False):
            return self.get_response(request)
        cookie_name = settings.ACCOUNT_SESSION_COOKIE_NAME
        raw_token = request.COOKIES.get(cookie_name, "")
        invalid_cookie = False
        if raw_token:
            if not 20 <= len(raw_token) <= 200:
                invalid_cookie = True
            else:
                session = (
                    LoginSession.objects.select_related("account")
                    .filter(token_digest=session_token_digest(raw_token))
                    .first()
                )
                now = timezone.now()
                if (
                    session is None
                    or not session.is_active(now=now)
                    or session.account.status != "ACTIVE"
                ):
                    invalid_cookie = True
                else:
                    request.account_id = session.account_id
                    request.account = session.account
                    request.login_session = session
                    if session.last_seen_at <= now - timedelta(minutes=5):
                        LoginSession.objects.filter(
                            pk=session.pk, last_seen_at=session.last_seen_at
                        ).update(last_seen_at=now)
                        session.last_seen_at = now
        response = self.get_response(request)
        if invalid_cookie and hasattr(response, "delete_cookie"):
            response.delete_cookie(
                cookie_name,
                path="/",
                samesite="Lax",
            )
        return response
