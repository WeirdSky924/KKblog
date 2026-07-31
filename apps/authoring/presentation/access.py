from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from apps.content.public import authoring_access
from apps.core.http import HTMX_VARIANT_HEADERS, is_htmx_fragment_request


def private_response(response: HttpResponse) -> HttpResponse:
    response.headers["Cache-Control"] = "private, no-store"
    patch_vary_headers(response, HTMX_VARIANT_HEADERS)
    return response


def login_required(request):
    target = (
        f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}"
    )
    if is_htmx_fragment_request(request):
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
