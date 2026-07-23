from django.http import Http404
from django.shortcuts import render

from apps.discovery.presentation.forms import HomePageForm
from apps.discovery.profile_identity import resolve_profile_identity
from apps.discovery.queries import home_article_page


def home(request):
    form = HomePageForm(request.GET)
    index_page = None
    pagination_query = ""
    status = 200
    if form.is_valid():
        index_page = home_article_page(
            actor_id=getattr(request, "account_id", None),
            page=form.cleaned_data["page"],
            page_size=form.cleaned_data["per_page"],
        )
        query = request.GET.copy()
        query.pop("page", None)
        query["per_page"] = str(index_page.page_size)
        pagination_query = query.urlencode()
    else:
        status = 422
    context = {
        "pagination_form": form,
        "index_page": index_page,
        "pagination_query": pagination_query,
    }
    template = (
        "discovery/partials/article_index.html"
        if request.headers.get("HX-Request") == "true"
        else "discovery/home.html"
    )
    return render(request, template, context, status=status)


def search(request):
    query = request.GET.get("q", "").strip()[:100]
    return render(
        request,
        "discovery/search.html",
        {"query": query, "search_pending": bool(query)},
        status=503 if query else 200,
    )


def article_placeholder(request, article_id):
    del request, article_id
    raise Http404 from None


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
