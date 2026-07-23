from urllib.parse import urlencode

from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.content.public import ArticleLoginRequired, ArticleNotFound
from apps.discovery.presentation.forms import (
    BookmarkStateForm,
    HomePageForm,
    PaginationForm,
    SearchPageForm,
)
from apps.discovery.queries import (
    article_detail_page,
    bookmark_page,
    discovery_filters,
    home_article_page,
    profile_article_page,
    search_article_page,
    section_article_page,
    tag_article_page,
)
from apps.discovery.services import (
    BookmarkCommandError,
    is_bookmarked,
    record_article_view,
    set_bookmark,
)


def _actor_id(request):
    return getattr(request, "account_id", None)


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _login_url(next_path: str) -> str:
    return f"{reverse('accounts:login')}?{urlencode({'next': next_path})}"


def _login_required_response(request, *, next_path: str):
    login_url = _login_url(next_path)
    if _is_htmx(request):
        response = HttpResponse(status=204)
        response.headers["HX-Redirect"] = login_url
    else:
        response = redirect(login_url)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _bookmark_control_context(
    *, actor_id, article_id: str, article_path: str, message: str = "", error: str = ""
):
    if actor_id is None:
        return {
            "bookmark_article_id": article_id,
            "bookmark_is_saved": False,
            "bookmark_login_url": _login_url(article_path),
            "bookmark_message": message,
            "bookmark_error": error,
        }
    return {
        "bookmark_article_id": article_id,
        "bookmark_is_saved": is_bookmarked(
            account_id=actor_id,
            article_id=article_id,
        ),
        "bookmark_login_url": None,
        "bookmark_message": message,
        "bookmark_error": error,
    }


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


@require_GET
def article_detail(request, article_id):
    article_path = reverse("article:detail", kwargs={"article_id": article_id})
    actor_id = _actor_id(request)
    try:
        page = article_detail_page(actor_id=actor_id, article_id=article_id)
    except ArticleLoginRequired:
        response = render(
            request,
            "discovery/article_login_required.html",
            {"login_url": _login_url(article_path)},
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except ArticleNotFound:
        raise Http404 from None
    view_count = record_article_view(article_id=page.article_id)
    response = render(
        request,
        "discovery/article_detail.html",
        {
            "article": page,
            "view_count": view_count,
            "permalink": request.build_absolute_uri(article_path),
            **_bookmark_control_context(
                actor_id=actor_id,
                article_id=page.article_id,
                article_path=article_path,
            ),
        },
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_POST
def article_bookmark(request, article_id):
    article_path = reverse("article:detail", kwargs={"article_id": article_id})
    bookmarks_path = reverse("accounts:bookmarks")
    source = (
        BookmarkStateForm.Source.BOOKMARKS
        if request.POST.get("source") == BookmarkStateForm.Source.BOOKMARKS
        else BookmarkStateForm.Source.ARTICLE
    )
    next_path = (
        bookmarks_path if source == BookmarkStateForm.Source.BOOKMARKS else article_path
    )
    actor_id = _actor_id(request)
    if actor_id is None:
        return _login_required_response(request, next_path=next_path)

    form = BookmarkStateForm(request.POST)
    message = ""
    error = ""
    status = 200
    if form.is_valid():
        desired = (
            form.cleaned_data["target_state"] == BookmarkStateForm.TargetState.SAVED
        )
        try:
            state = set_bookmark(
                account_id=actor_id,
                article_id=article_id,
                bookmarked=desired,
            )
        except (ArticleLoginRequired, ArticleNotFound):
            raise Http404 from None
        except BookmarkCommandError as exc:
            error = exc.safe_message
            status = 422
        else:
            message = "已收藏。" if state.bookmarked else "已移除收藏。"
    else:
        error = next(
            (str(item) for errors in form.errors.values() for item in errors),
            "收藏状态无效。",
        )
        status = 422

    if status == 200 and source == BookmarkStateForm.Source.BOOKMARKS:
        response = redirect(bookmarks_path)
    elif status == 200 and not _is_htmx(request):
        response = redirect(article_path)
    else:
        response = render(
            request,
            "discovery/partials/bookmark_control.html",
            _bookmark_control_context(
                actor_id=actor_id,
                article_id=article_id,
                article_path=article_path,
                message=message,
                error=error,
            ),
            status=status,
        )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def bookmarks(request):
    bookmarks_path = reverse("accounts:bookmarks")
    actor_id = _actor_id(request)
    if actor_id is None:
        return _login_required_response(request, next_path=bookmarks_path)
    form = PaginationForm(request.GET)
    valid = form.is_valid()
    page = bookmark_page(
        account_id=actor_id,
        page=form.cleaned_data["page"] if valid else 1,
        page_size=form.cleaned_data["per_page"] if valid else 20,
    )
    response = render(
        request,
        (
            "discovery/partials/bookmark_list.html"
            if _is_htmx(request)
            else "discovery/bookmarks.html"
        ),
        {
            "bookmark_page": page,
            "pagination_form": form,
            "index_page": page,
            "index_action": bookmarks_path,
            "pagination_query": _pagination_query(request, page.page_size)
            if valid
            else "",
        },
        status=200 if valid else 422,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def public_profile(request, account_id):
    form = PaginationForm(request.GET)
    valid = form.is_valid()
    page = profile_article_page(
        actor_id=_actor_id(request),
        account_id=account_id,
        page=form.cleaned_data["page"] if valid else 1,
        page_size=form.cleaned_data["per_page"] if valid else 20,
    )
    if page is None:
        raise Http404 from None
    profile_url = reverse("public:profile", kwargs={"account_id": account_id})
    response = render(
        request,
        _page_template(request, "discovery/public_profile.html"),
        {
            "profile": page.identity,
            "pagination_form": form,
            "index_page": page.index_page,
            "pagination_query": (
                _pagination_query(request, page.index_page.page_size) if valid else ""
            ),
            "index_action": profile_url,
            "selected_tag_ids": (),
            "index_empty_title": "此处还没有公开文章",
            "index_empty_action_url": reverse("public:home"),
            "index_empty_action_label": "浏览最新文章",
        },
        status=200 if valid else 422,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
