import json
from urllib.parse import urlencode

from django.http import HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET, require_POST

from apps.core.http import HTMX_VARIANT_HEADERS, is_htmx_fragment_request

from .forms import OpportunityBookmarkForm, OpportunityPageForm
from .public import (
    OpportunityCommandError,
    public_opportunities,
    public_opportunity_filters,
    public_opportunity_sources,
    public_opportunity_summary,
    set_opportunity_bookmark,
)

JOB_FILTER_PARAMETERS = (
    "job_q",
    "cities",
    "statuses",
    "companies",
    "recruitment_types",
    "categories",
    "cohorts",
    "bookmarked",
)
SOURCE_FILTER_PARAMETERS = ("source_q", "source_types")
BOOKMARKS_RESET_PARAMETERS = (
    *JOB_FILTER_PARAMETERS,
    *SOURCE_FILTER_PARAMETERS,
    "job_page",
    "source_page",
)


def _actor(request):
    return getattr(request, "account_id", None)


def _login_url(next_path):
    return f"{reverse('accounts:login')}?{urlencode({'next': next_path})}"


def _safe_return_path(value):
    if (
        value.startswith("/opportunities/")
        and not value.startswith("//")
        and "\\" not in value
    ):
        return value
    return reverse("opportunities:index")


def _query_url(query, *, view=None, remove=()):
    values = query.copy()
    for name in remove:
        values.pop(name, None)
    if view:
        values["view"] = view
    encoded = values.urlencode()
    base = reverse("opportunities:index")
    return f"{base}?{encoded}" if encoded else base


def _pagination_query(request, view):
    query = request.GET.copy()
    query.pop("job_page" if view in {"jobs", "bookmarks"} else "source_page", None)
    return query.urlencode()


def _preserved_fields(request, view):
    excluded = {"view", "per_page"}
    excluded.update(
        JOB_FILTER_PARAMETERS
        if view in {"jobs", "bookmarks"}
        else SOURCE_FILTER_PARAMETERS
    )
    excluded.add("job_page" if view in {"jobs", "bookmarks"} else "source_page")
    return tuple(
        (name, value)
        for name in request.GET
        if name not in excluded
        for value in request.GET.getlist(name)
    )


def _page_size_fields(request, view):
    current_page = "job_page" if view in {"jobs", "bookmarks"} else "source_page"
    return tuple(
        (name, value)
        for name in request.GET
        if name not in {"per_page", current_page}
        for value in request.GET.getlist(name)
    )


def _default_query(filters):
    query = QueryDict(mutable=True)
    query["view"] = "jobs"
    for name, values in (
        ("cities", filters.default_city_ids),
        ("statuses", filters.default_verification_statuses),
        ("companies", filters.default_source_ids),
        ("recruitment_types", filters.default_recruitment_types),
        ("categories", filters.default_category_ids),
        ("cohorts", filters.default_cohort_ids),
    ):
        if values:
            query.setlist(name, tuple(str(value) for value in values))
    return query


def _active_filter_count(values):
    if values["view"] == "sources":
        return len(values["source_types"]) + int(bool(values["source_q"]))
    return (
        sum(
            len(values[name])
            for name in (
                "cities",
                "statuses",
                "companies",
                "recruitment_types",
                "categories",
                "cohorts",
            )
        )
        + int(values["bookmarked"])
        + int(bool(values["job_q"]))
    )


def _context(request):
    actor_id = _actor(request)
    filters = public_opportunity_filters()
    form = OpportunityPageForm(
        request.GET,
        filters=filters,
        authenticated=actor_id is not None,
    )
    jobs = sources = None
    status = 200
    active_filters = 0
    view = request.GET.get("view", "jobs")
    if form.is_valid():
        values = form.cleaned_data
        view = values["view"]
        active_filters = _active_filter_count(values)
        if view in {"jobs", "bookmarks"}:
            jobs = public_opportunities(
                actor_id=actor_id,
                query=values["job_q"],
                city_ids=values["cities"],
                verification_statuses=values["statuses"],
                source_ids=values["companies"],
                recruitment_types=values["recruitment_types"],
                category_ids=values["categories"],
                cohort_ids=values["cohorts"],
                bookmarked_only=(view == "bookmarks" or values["bookmarked"]),
                page=values["job_page"],
                page_size=values["per_page"],
            )
        else:
            sources = public_opportunity_sources(
                query=values["source_q"],
                source_types=values["source_types"],
                page=values["source_page"],
                page_size=values["per_page"],
            )
    else:
        status = 422
        if view not in {"jobs", "sources", "bookmarks"}:
            view = "jobs"
    current_path = request.get_full_path()
    bookmark_path = _query_url(
        request.GET, view="bookmarks", remove=BOOKMARKS_RESET_PARAMETERS
    )
    clear_parameters = (
        (*JOB_FILTER_PARAMETERS, "job_page")
        if view in {"jobs", "bookmarks"}
        else (*SOURCE_FILTER_PARAMETERS, "source_page")
    )
    return {
        "opportunity_form": form,
        "opportunity_filters": filters,
        "opportunity_summary": public_opportunity_summary(),
        "opportunity_jobs": jobs,
        "opportunity_sources": sources,
        "opportunity_view": view,
        "opportunity_active_filters": active_filters,
        "opportunity_pagination_query": _pagination_query(request, view),
        "opportunity_preserved_fields": _preserved_fields(request, view),
        "opportunity_page_size_fields": _page_size_fields(request, view),
        "opportunity_jobs_url": _query_url(request.GET, view="jobs"),
        "opportunity_sources_url": _query_url(request.GET, view="sources"),
        "opportunity_bookmarks_path": bookmark_path,
        "opportunity_bookmarks_login_url": _login_url(bookmark_path),
        "opportunity_clear_url": _query_url(
            request.GET, view=view, remove=clear_parameters
        ),
        "opportunity_current_path": current_path,
        "opportunity_login_url": _login_url(current_path),
        "opportunity_authenticated": actor_id is not None,
        "status": status,
    }


@require_GET
def opportunities(request):
    if not request.GET:
        query = _default_query(public_opportunity_filters()).urlencode()
        return redirect(f"{reverse('opportunities:index')}?{query}")
    if request.GET.get("view") == "bookmarks" and _actor(request) is None:
        return redirect(_login_url(_query_url(request.GET, view="bookmarks")))
    context = _context(request)
    status = context.pop("status")
    template = (
        "opportunities/partials/workspace.html"
        if is_htmx_fragment_request(request)
        else "opportunities/index.html"
    )
    response = render(request, template, context, status=status)
    response.headers["Cache-Control"] = "private, no-store"
    patch_vary_headers(response, (*HTMX_VARIANT_HEADERS, "Cookie"))
    return response


@require_POST
def opportunity_bookmark(request):
    next_path = _safe_return_path(request.POST.get("return_query", ""))
    actor_id = _actor(request)
    if actor_id is None:
        login_url = _login_url(next_path)
        if not is_htmx_fragment_request(request):
            return redirect(login_url)
        response = HttpResponse(status=204)
        response.headers["HX-Redirect"] = login_url
        return response
    form = OpportunityBookmarkForm(request.POST)
    if not form.is_valid():
        return HttpResponse("收藏请求无效。", status=422)
    try:
        selected = set_opportunity_bookmark(
            account_id=actor_id,
            opportunity_id=form.cleaned_data["opportunity_id"],
            selected=form.cleaned_data["selected"],
        )
    except OpportunityCommandError as error:
        return HttpResponse(error.safe_message, status=422)
    if not is_htmx_fragment_request(request):
        return redirect(next_path)
    response = render(
        request,
        "opportunities/partials/bookmark_button.html",
        {
            "bookmark_opportunity_id": form.cleaned_data["opportunity_id"],
            "bookmark_selected": selected,
            "opportunity_current_path": next_path,
        },
    )
    response.headers["HX-Trigger"] = json.dumps(
        {
            "kaj:feedback": {
                "message": "岗位已收藏" if selected else "已取消岗位收藏",
                "level": "success" if selected else "info",
                "timeout": 4000,
            }
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return response


__all__ = ["opportunities", "opportunity_bookmark"]
