from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..queries import published_static_page, visible_friend_links


def _static_page(request: HttpRequest, page_type: str) -> HttpResponse:
    page = published_static_page(page_type)
    if page is None:
        raise Http404
    return render(
        request,
        "navigation/static_page.html",
        {"static_page": page},
    )


@require_GET
def about_page(request: HttpRequest) -> HttpResponse:
    return _static_page(request, "ABOUT")


@require_GET
def privacy_page(request: HttpRequest) -> HttpResponse:
    return _static_page(request, "PRIVACY")


@require_GET
def terms_page(request: HttpRequest) -> HttpResponse:
    return _static_page(request, "TERMS")


@require_GET
def friend_links_page(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "navigation/friend_links.html",
        {"friend_links": visible_friend_links()},
    )


__all__ = [
    "about_page",
    "friend_links_page",
    "privacy_page",
    "terms_page",
]
