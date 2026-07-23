from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from apps.discovery.presentation.forms import (
    HomePageForm,
    PaginationForm,
    SearchPageForm,
)
from apps.discovery.profile_identity import resolve_profile_identity
from apps.discovery.queries import (
    discovery_filters,
    home_article_page,
    search_article_page,
    section_article_page,
    tag_article_page,
)


def _actor_id(request):
    return getattr(request, "account_id", None)


def _pagination_query(request, page_size: int, *, tag_ids=None) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    query["per_page"] = str(page_size)
    if tag_ids is not None:
        query.pop("tags", None)
        for tag_id in tag_ids:
            query.appendlist("tags", str(tag_id))
    return query.urlencode()


def _page_template(request, page_template: str) -> str:
    if request.headers.get("HX-Request") == "true":
        return "discovery/partials/article_index.html"
    return page_template


def home(request):
    actor_id = _actor_id(request)
    filter_options = discovery_filters(actor_id=actor_id)
    form = HomePageForm(
        request.GET,
        tag_choices=(
            (str(option.filter_id), option.name) for option in filter_options.tags
        ),
    )
    index_page = None
    pagination_query = ""
    selected_tag_ids = tuple(request.GET.getlist("tags"))
    status = 200
    if form.is_valid():
        selected_tag_ids = form.cleaned_data["tags"]
        index_page = home_article_page(
            actor_id=actor_id,
            page=form.cleaned_data["page"],
            page_size=form.cleaned_data["per_page"],
            tag_ids=selected_tag_ids,
        )
        pagination_query = _pagination_query(
            request,
            index_page.page_size,
            tag_ids=selected_tag_ids,
        )
    else:
        status = 422
    context = {
        "filter_options": filter_options,
        "pagination_form": form,
        "index_page": index_page,
        "pagination_query": pagination_query,
        "index_action": reverse("public:home"),
        "clear_filter_url": reverse("public:home"),
        "selected_tag_ids": selected_tag_ids,
    }
    return render(
        request,
        _page_template(request, "discovery/home.html"),
        context,
        status=status,
    )


def _collection_page(request, *, identity, loader, route_name, template):
    form = PaginationForm(request.GET)
    valid = form.is_valid()
    page = form.cleaned_data["page"] if valid else 1
    page_size = form.cleaned_data["per_page"] if valid else 20
    collection = loader(
        actor_id=_actor_id(request),
        page=page,
        page_size=page_size,
        **identity,
    )
    if collection is None:
        raise Http404 from None
    context = {
        "collection": collection,
        "pagination_form": form,
        "index_page": collection.index_page,
        "pagination_query": (
            _pagination_query(request, collection.index_page.page_size) if valid else ""
        ),
        "index_action": reverse(route_name, kwargs=identity),
        "selected_tag_ids": (),
    }
    return render(
        request,
        _page_template(request, template),
        context,
        status=200 if valid else 422,
    )


def section(request, section_id):
    return _collection_page(
        request,
        identity={"section_id": section_id},
        loader=section_article_page,
        route_name="public:section",
        template="discovery/section.html",
    )


def tag(request, tag_id):
    return _collection_page(
        request,
        identity={"tag_id": tag_id},
        loader=tag_article_page,
        route_name="public:tag",
        template="discovery/tag.html",
    )


def search(request):
    requested = "q" in request.GET
    form = SearchPageForm(request.GET if requested else None)
    index_page = None
    pagination_query = ""
    search_query = None
    status = 200
    if requested and form.is_valid():
        search_query = form.cleaned_data["q"]
        index_page = search_article_page(
            actor_id=_actor_id(request),
            query=search_query,
            page=form.cleaned_data["page"],
            page_size=form.cleaned_data["per_page"],
        )
        pagination_query = _pagination_query(request, index_page.page_size)
    elif requested:
        status = 422
    context = {
        "pagination_form": form,
        "index_page": index_page,
        "pagination_query": pagination_query,
        "index_action": reverse("public:search"),
        "selected_tag_ids": (),
        "search_query": search_query,
        "index_initial_prompt": "输入文章标题开始搜索。" if not requested else None,
    }
    return render(
        request,
        _page_template(request, "discovery/search.html"),
        context,
        status=status,
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
