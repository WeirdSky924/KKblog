from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import render

from apps.authoring.presenters import article_workspace
from apps.content.public import ArticleNotFound

from .access import author_id_or_response, private_response


def articles(request):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
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
        return private_response(HttpResponseNotAllowed(("GET",)))
    template = (
        "authoring/partials/article_workspace.html"
        if request.headers.get("HX-Request") == "true"
        else "authoring/articles.html"
    )
    return private_response(render(request, template, {"workspace": workspace}))
