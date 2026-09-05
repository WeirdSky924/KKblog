from urllib.parse import urlencode

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.comments.public import article_comment_context
from apps.content.public import (
    ArticleLoginRequired,
    ArticleNotFound,
    search_visible_titles,
)
from apps.core.http import is_htmx_fragment_request
from apps.discovery.presentation.forms import (
    ArticleLikeStateForm,
    BookmarkStateForm,
    HomePageForm,
    PaginationForm,
    ProfilePageForm,
    ReadingBookmarkProgressForm,
    SearchCategory,
    SearchPageForm,
    SearchSuggestionForm,
)
from apps.discovery.profile_identity import (
    resolve_profile_identities,
    search_profile_identities,
)
from apps.discovery.queries import (
    article_detail_page,
    article_like_count,
    author_search_page,
    bookmark_page,
    discovery_filters,
    home_article_page,
    profile_article_page,
    search_article_page,
    section_article_page,
    tag_article_page,
)
from apps.discovery.services import (
    ArticleLikeCommandError,
    ArticleLikeUnavailableError,
    BookmarkCommandError,
    ReadingBookmarkCommandError,
    ReadingBookmarkUnavailableError,
    is_article_liked,
    is_bookmarked,
    reading_bookmark_progress,
    record_article_view,
    save_reading_bookmark,
    set_article_like,
    set_bookmark,
)


def _actor_id(request):
    return getattr(request, "account_id", None)


def _login_url(next_path: str) -> str:
    return f"{reverse('accounts:login')}?{urlencode({'next': next_path})}"


def _login_required_response(request, *, next_path: str):
    login_url = _login_url(next_path)
    if is_htmx_fragment_request(request):
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


def _like_control_context(
    *, actor_id, article_id: str, article_path: str, message: str = "", error: str = ""
):
    count = article_like_count(article_id=article_id)
    if actor_id is None:
        return {
            "like_article_id": article_id,
            "like_is_saved": False,
            "like_count": count,
            "like_login_url": _login_url(article_path),
            "like_message": message,
            "like_error": error,
        }
    return {
        "like_article_id": article_id,
        "like_is_saved": is_article_liked(
            account_id=actor_id,
            article_id=article_id,
        ),
        "like_count": count,
        "like_login_url": None,
        "like_message": message,
        "like_error": error,
    }


def _reading_bookmark_context(
    *, actor_id, article_id: str, article_path: str
) -> dict[str, object]:
    if actor_id is None:
        return {
            "reading_bookmark_progress": None,
            "reading_bookmark_progress_value": "",
            "reading_bookmark_login_url": _login_url(article_path),
        }
    progress = reading_bookmark_progress(
        account_id=actor_id,
        article_id=article_id,
    )
    return {
        "reading_bookmark_progress": progress,
        "reading_bookmark_progress_value": (
            f"{progress:.6f}" if progress is not None else ""
        ),
        "reading_bookmark_login_url": None,
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


def _pagination_page_size_fields(
    request, *, tag_ids=None
) -> tuple[tuple[str, str], ...]:
    query = request.GET.copy()
    query.pop("page", None)
    query.pop("per_page", None)
    if tag_ids is not None:
        query.pop("tags", None)
        for tag_id in tag_ids:
            query.appendlist("tags", str(tag_id))
    return tuple((name, value) for name in query for value in query.getlist(name))


def _page_template(request, page_template: str) -> str:
    if is_htmx_fragment_request(request):
        return "discovery/partials/article_index.html"
    return page_template


def _no_store(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def home(request):
    actor_id = _actor_id(request)
    # Sections are already represented by the homepage navigation. Avoid loading
    # the full section/cover catalog when only the tag picker is rendered here.
    filter_options = discovery_filters(actor_id=actor_id, include_sections=False)
    form = HomePageForm(
        request.GET,
        tag_choices=(
            (str(option.filter_id), option.name) for option in filter_options.tags
        ),
    )
    index_page = None
    pagination_query = ""
    pagination_page_size_fields: tuple[tuple[str, str], ...] = ()
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
        pagination_page_size_fields = _pagination_page_size_fields(
            request,
            tag_ids=selected_tag_ids,
        )
    else:
        status = 422
    context = {
        "filter_options": filter_options,
        "pagination_form": form,
        "index_page": index_page,
        "pagination_query": pagination_query,
        "pagination_page_size_fields": pagination_page_size_fields,
        "index_action": reverse("public:home"),
        "clear_filter_url": reverse("public:home"),
        "selected_tag_ids": selected_tag_ids,
        "sections_managed_by_navigation": True,
        "home_article_heading": "最新文章",
        "home_article_jump_label": "查看最新文章",
        "home_article_refresh_url": request.get_full_path(),
        "active_home_section_id": None,
    }
    return _no_store(
        render(
            request,
            (
                "discovery/partials/home_article_region.html"
                if is_htmx_fragment_request(request)
                and request.headers.get("HX-Target") == "home-article-region"
                else _page_template(request, "discovery/home.html")
            ),
            context,
            status=status,
        )
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
        "pagination_page_size_fields": (
            _pagination_page_size_fields(request) if valid else ()
        ),
        "index_action": reverse(route_name, kwargs=identity),
        "selected_tag_ids": (),
    }
    return _no_store(
        render(
            request,
            _page_template(request, template),
            context,
            status=200 if valid else 422,
        )
    )


def section(request, section_id):
    form = PaginationForm(request.GET)
    valid = form.is_valid()
    page = form.cleaned_data["page"] if valid else 1
    page_size = form.cleaned_data["per_page"] if valid else 20
    collection = section_article_page(
        actor_id=_actor_id(request),
        section_id=section_id,
        page=page,
        page_size=page_size,
    )
    if collection is None:
        raise Http404 from None
    section_url = reverse("public:section", kwargs={"section_id": section_id})
    context = {
        "collection": collection,
        "pagination_form": form,
        "index_page": collection.index_page,
        "pagination_query": (
            _pagination_query(request, collection.index_page.page_size) if valid else ""
        ),
        "pagination_page_size_fields": (
            _pagination_page_size_fields(request) if valid else ()
        ),
        "index_action": section_url,
        "selected_tag_ids": (),
        "sections_managed_by_navigation": True,
        "home_article_heading": collection.name,
        "home_article_jump_label": f"查看{collection.name}文章",
        "home_article_refresh_url": request.get_full_path(),
        "home_section_name": collection.name,
        "active_home_section_id": str(section_id),
    }
    if is_htmx_fragment_request(request):
        template = (
            "discovery/partials/home_article_region.html"
            if request.headers.get("HX-Target") == "home-article-region"
            else "discovery/partials/article_index.html"
        )
    else:
        template = "discovery/home.html"
    return _no_store(render(request, template, context, status=200 if valid else 422))


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
    pagination_page_size_fields: tuple[tuple[str, str], ...] = ()
    search_query = None
    search_type = SearchCategory.ARTICLE
    status = 200
    if requested and form.is_valid():
        search_query = form.cleaned_data["q"]
        search_type = form.cleaned_data["type"]
        if search_type == SearchCategory.AUTHOR:
            index_page = author_search_page(
                query=search_query,
                page=form.cleaned_data["page"],
                page_size=form.cleaned_data["per_page"],
            )
        else:
            index_page = search_article_page(
                actor_id=_actor_id(request),
                query=search_query,
                page=form.cleaned_data["page"],
                page_size=form.cleaned_data["per_page"],
            )
        pagination_query = _pagination_query(request, index_page.page_size)
        pagination_page_size_fields = _pagination_page_size_fields(request)
    elif requested:
        if request.GET.get("type") == SearchCategory.AUTHOR:
            search_type = SearchCategory.AUTHOR
        status = 422
    context = {
        "pagination_form": form,
        "index_page": index_page,
        "pagination_query": pagination_query,
        "pagination_page_size_fields": pagination_page_size_fields,
        "index_action": reverse("public:search"),
        "selected_tag_ids": (),
        "search_query": search_query,
        "search_type": search_type,
        "search_type_label": "作者" if search_type == SearchCategory.AUTHOR else "文章",
        "index_initial_prompt": (
            (
                "输入作者昵称开始搜索。"
                if search_type == SearchCategory.AUTHOR
                else "输入文章标题开始搜索。"
            )
            if not requested
            else None
        ),
    }
    template = (
        (
            "discovery/partials/author_search_results.html"
            if search_type == SearchCategory.AUTHOR
            else "discovery/partials/article_index.html"
        )
        if is_htmx_fragment_request(request)
        else "discovery/search.html"
    )
    return _no_store(
        render(
            request,
            template,
            context,
            status=status,
        )
    )


@require_GET
def search_suggestions(request):
    if _actor_id(request) is None:
        return _no_store(JsonResponse({"items": []}))
    if not request.GET.get("q", "").strip():
        return _no_store(JsonResponse({"items": []}))
    form = SearchSuggestionForm(request.GET)
    if not form.is_valid():
        return _no_store(
            JsonResponse(
                {"items": [], "error": "搜索条件无效。"},
                status=422,
            )
        )
    query = form.cleaned_data["q"]
    search_type = form.cleaned_data["type"]
    if search_type == SearchCategory.AUTHOR:
        items = [
            {
                "label": identity.display_name,
                "description": "作者",
                "url": identity.profile_url,
                "image_url": identity.avatar_url or "",
                "initial": identity.avatar_initial,
            }
            for identity in search_profile_identities(query=query, limit=5)
        ]
    else:
        source = search_visible_titles(
            actor_id=_actor_id(request),
            query=query,
            page=1,
            page_size=10,
        )
        visible = source.items[:5]
        authors = resolve_profile_identities(tuple(item.author_id for item in visible))
        items = [
            {
                "label": item.title,
                "description": (
                    f"@{authors[item.author_id].display_name} · 文章"
                    if item.author_id in authors
                    else "文章"
                ),
                "url": reverse(
                    "article:detail", kwargs={"article_id": item.article_id}
                ),
                "section": item.section_name or "",
                "tags": [tag.name for tag in item.tags],
            }
            for item in visible
        ]
    return _no_store(JsonResponse({"items": items}))


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
            **_like_control_context(
                actor_id=actor_id,
                article_id=page.article_id,
                article_path=article_path,
            ),
            **_reading_bookmark_context(
                actor_id=actor_id,
                article_id=page.article_id,
                article_path=article_path,
            ),
            **article_comment_context(
                request=request,
                article_id=page.article_id,
            ),
        },
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_POST
def article_reading_bookmark(request, article_id):
    article_path = reverse("article:detail", kwargs={"article_id": article_id})
    actor_id = _actor_id(request)
    if actor_id is None:
        return _login_required_response(request, next_path=article_path)

    form = ReadingBookmarkProgressForm(request.POST)
    if not form.is_valid():
        return _no_store(
            JsonResponse(
                {"ok": False, "error": "阅读位置无效。"},
                status=422,
            )
        )
    try:
        state = save_reading_bookmark(
            account_id=actor_id,
            article_id=article_id,
            progress=form.cleaned_data["progress"],
        )
    except (ArticleLoginRequired, ArticleNotFound):
        raise Http404 from None
    except ReadingBookmarkUnavailableError as exc:
        return _no_store(
            JsonResponse(
                {"ok": False, "error": exc.safe_message},
                status=503,
            )
        )
    except ReadingBookmarkCommandError as exc:
        return _no_store(
            JsonResponse(
                {"ok": False, "error": exc.safe_message},
                status=422,
            )
        )
    return _no_store(
        JsonResponse(
            {
                "ok": True,
                "progress": f"{state.progress:.6f}",
                "created": state.created,
            }
        )
    )


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
    elif status == 200 and not is_htmx_fragment_request(request):
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


@require_POST
def article_like(request, article_id):
    article_path = reverse("article:detail", kwargs={"article_id": article_id})
    actor_id = _actor_id(request)
    if actor_id is None:
        return _login_required_response(request, next_path=article_path)

    form = ArticleLikeStateForm(request.POST)
    message = ""
    error = ""
    status = 200
    if form.is_valid():
        desired = (
            form.cleaned_data["target_state"] == ArticleLikeStateForm.TargetState.LIKED
        )
        try:
            state = set_article_like(
                account_id=actor_id,
                article_id=article_id,
                liked=desired,
            )
        except (ArticleLoginRequired, ArticleNotFound):
            raise Http404 from None
        except ArticleLikeUnavailableError as exc:
            error = exc.safe_message
            status = 503
        except ArticleLikeCommandError as exc:
            error = exc.safe_message
            status = 422
        else:
            message = "已点赞。" if state.liked else "已取消点赞。"
    else:
        error = next(
            (str(item) for errors in form.errors.values() for item in errors),
            "点赞状态无效。",
        )
        status = 422

    if status == 200 and not is_htmx_fragment_request(request):
        response = redirect(article_path)
    else:
        response = render(
            request,
            "discovery/partials/like_control.html",
            _like_control_context(
                actor_id=actor_id,
                article_id=article_id,
                article_path=article_path,
                message=message,
                error=error,
            ),
            status=status,
        )
        if status >= 500:
            response.headers["X-Kaj-Inline-Error"] = "true"
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
            if is_htmx_fragment_request(request)
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
            "pagination_page_size_fields": (
                _pagination_page_size_fields(request) if valid else ()
            ),
        },
        status=200 if valid else 422,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def public_profile(request, account_id):
    actor_id = _actor_id(request)
    filter_options = discovery_filters(actor_id=actor_id)
    form = ProfilePageForm(
        request.GET,
        section_choices=(
            (str(option.filter_id), option.name) for option in filter_options.sections
        ),
        tag_choices=(
            (str(option.filter_id), option.name) for option in filter_options.tags
        ),
    )
    valid = form.is_valid()
    selected_section_id = form.cleaned_data["section"] if valid else None
    selected_tag_ids = form.cleaned_data["tags"] if valid else ()
    page = profile_article_page(
        actor_id=actor_id,
        account_id=account_id,
        page=form.cleaned_data["page"] if valid else 1,
        page_size=form.cleaned_data["per_page"] if valid else 20,
        section_id=selected_section_id,
        tag_ids=selected_tag_ids,
        include_stats=not is_htmx_fragment_request(request),
    )
    if page is None:
        raise Http404 from None
    profile_url = reverse("public:profile", kwargs={"account_id": account_id})
    response = render(
        request,
        _page_template(request, "discovery/public_profile.html"),
        {
            "profile": page.identity,
            "profile_stats": page.stats,
            "filter_options": filter_options,
            "pagination_form": form,
            "index_page": page.index_page,
            "pagination_query": (
                _pagination_query(
                    request,
                    page.index_page.page_size,
                    tag_ids=selected_tag_ids,
                )
                if valid
                else ""
            ),
            "pagination_page_size_fields": (
                _pagination_page_size_fields(request, tag_ids=selected_tag_ids)
                if valid
                else ()
            ),
            "index_action": profile_url,
            "clear_filter_url": profile_url,
            "selected_section_id": selected_section_id,
            "selected_tag_ids": selected_tag_ids,
            "profile_filter_mode": True,
            "index_empty_title": (
                "没有符合筛选条件的文章"
                if selected_section_id or selected_tag_ids
                else "此处还没有公开文章"
            ),
            "index_empty_action_url": (
                profile_url
                if selected_section_id or selected_tag_ids
                else reverse("public:home")
            ),
            "index_empty_action_label": (
                "清除筛选"
                if selected_section_id or selected_tag_ids
                else "浏览最新文章"
            ),
        },
        status=200 if valid else 422,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
