from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.presentation.forms import AdminPasswordResetForm
from apps.accounts.services.admin_password_reset import (
    AdminPasswordResetError,
    reset_password_with_admin_link,
)


def _render_reset_link_page(
    request: HttpRequest, *, form: AdminPasswordResetForm | None = None, status=200
) -> HttpResponse:
    response = render(
        request,
        "accounts/admin_password_reset.html",
        {
            "reset_form": form or AdminPasswordResetForm(),
            "disable_analytics": True,
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def admin_password_reset_link(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _render_reset_link_page(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    form = AdminPasswordResetForm(request.POST)
    if not form.is_valid():
        return _render_reset_link_page(request, form=form, status=422)
    try:
        reset_password_with_admin_link(
            token=form.cleaned_data["token"],
            new_password=form.cleaned_data["new_password"],
            client_ip=getattr(
                request, "client_ip", request.META.get("REMOTE_ADDR", "127.0.0.1")
            ),
            trace_code=getattr(request, "trace_code", ""),
        )
    except AdminPasswordResetError as exc:
        form.add_error(None, str(exc))
        return _render_reset_link_page(request, form=form, status=422)
    response = redirect(f"{reverse('accounts:login')}?reset=1")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
