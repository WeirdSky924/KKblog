from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from apps.content.public import authoring_access


def private_response(response: HttpResponse) -> HttpResponse:
    response.headers["Cache-Control"] = "private, no-store"
    patch_vary_headers(response, ("HX-Request",))
    return response


def login_required(request):
    target = (
        f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}"
    )
    if request.headers.get("HX-Request") == "true":
        response = private_response(HttpResponse(status=204))
        response.headers["HX-Redirect"] = target
        return response
    return private_response(redirect(target))


def author_id_or_response(request):
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return None, login_required(request)
    if not authoring_access(actor_id):
        raise PermissionDenied
    return actor_id, None
