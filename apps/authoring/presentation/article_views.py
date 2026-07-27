from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from apps.authoring.presenters import article_workspace
from apps.content.public import ArticleNotFound


def _private(response):
    response.headers["Cache-Control"] = "private, no-store"
    patch_vary_headers(response, ("HX-Request",))
    return response


def _login_required(request):
    target = (
        f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}"
    )
    if request.headers.get("HX-Request") == "true":
        response = _private(HttpResponse(status=204))
        response.headers["HX-Redirect"] = target
        return response
    return _private(redirect(target))


def articles(request):
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return _login_required(request)
    try:
        workspace = article_workspace(
            actor_id=actor_id,
            state=request.GET.get("state", "PUBLISHED"),
            page=request.GET.get("page", 1),
        )
    except ArticleNotFound:
        raise PermissionDenied from None
    except ValueError:
        raise Http404 from None
    if request.method != "GET":
        return _private(HttpResponseNotAllowed(("GET",)))
    template = (
        "authoring/partials/article_workspace.html"
        if request.headers.get("HX-Request") == "true"
        else "authoring/articles.html"
    )
    return _private(render(request, template, {"workspace": workspace}))
