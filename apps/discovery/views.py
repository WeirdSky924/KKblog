from django.http import Http404
from django.shortcuts import render

from apps.discovery.profile_identity import resolve_profile_identity


def home(request):
    return render(
        request,
        "discovery/home.html",
        {"signed_in": getattr(request, "account_id", None) is not None},
    )


def public_profile(request, account_id):
    identity = resolve_profile_identity(account_id)
    if identity is None:
        raise Http404 from None
    response = render(
        request,
        "discovery/public_profile.html",
        {"profile": identity},
    )
    response.headers["Cache-Control"] = "public, no-cache"
    return response
