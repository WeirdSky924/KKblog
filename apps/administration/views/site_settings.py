from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.comments.public import GuestbookSettingsError, update_guestbook_settings
from apps.navigation.public import (
    SiteContentCommandError,
    SiteContentQueryError,
    admin_site_settings,
    create_friend_link,
    delete_friend_link,
    set_trusted_embed_source,
    update_friend_link,
    update_site_configuration,
    update_static_page,
)

from ..presentation.site_settings import (
    SiteSettingsForms,
    build_site_settings_forms,
)


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


def _status(error: SiteContentCommandError | GuestbookSettingsError) -> int:
    code = getattr(error, "code", "")
    return 409 if "conflict" in code else 422


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    page_error: str = "",
    forms: SiteSettingsForms | None = None,
) -> HttpResponse:
    try:
        settings = admin_site_settings(actor_id=request.account_id)
    except PermissionError:
        raise PermissionDenied from None
    except SiteContentQueryError:
        response = render(
            request,
            "administration/site_settings.html",
            {
                "settings_unavailable": True,
                "page_error": "站点设置暂时不可用，请稍后重试。",
                "trace_code": getattr(request, "trace_code", ""),
            },
            status=503,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    form_bundle = forms or build_site_settings_forms(
        settings,
        actor_id=request.account_id,
    )
    response = render(
        request,
        "administration/site_settings.html",
        {
            "site_settings": settings,
            "site_settings_forms": form_bundle,
            "static_page_entries": tuple(
                (page, form_bundle.static_pages[page.page_type])
                for page in settings.static_pages
            ),
            "friend_link_entries": tuple(
                (
                    link,
                    form_bundle.friend_links[str(link.id)],
                    form_bundle.friend_delete[str(link.id)],
                )
                for link in settings.friend_links
            ),
            "trusted_source_entries": tuple(
                (source, form_bundle.trusted_sources[source.source_key])
                for source in settings.trusted_sources
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "media_upload_urls": {
                "site_logo": reverse("media:upload", kwargs={"adapter": "site-logo"}),
                "friend_logo": reverse(
                    "media:upload", kwargs={"adapter": "friend-logo"}
                ),
            },
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _bound(
    request: HttpRequest,
    *,
    settings,
    action: str,
    identity: str = "",
) -> SiteSettingsForms:
    return build_site_settings_forms(
        settings,
        actor_id=request.account_id,
        data=request.POST,
        bound_action=action,
        bound_id=identity,
    )


def _post_configuration(request: HttpRequest) -> HttpResponse:
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="configuration")
    form = forms.configuration
    if not form.is_valid():
        return _render(request, status=422, forms=forms, page_error="请修正站点设置。")
    try:
        update_site_configuration(
            actor_id=request.account_id,
            **form.cleaned_data,
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(
        f"{reverse('admin:site-settings')}?saved=configuration#site-configuration"
    )


def _post_static_page(request: HttpRequest) -> HttpResponse:
    page_type = request.POST.get("page_type", "")
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="static_page", identity=page_type)
    form = forms.static_pages.get(page_type)
    if form is None:
        return _render(
            request, status=422, forms=forms, page_error="静态页面类型不合法。"
        )
    if not form.is_valid():
        return _render(request, status=422, forms=forms, page_error="请修正页面正文。")
    try:
        update_static_page(
            actor_id=request.account_id,
            **form.cleaned_data,
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(f"{reverse('admin:site-settings')}?saved=page#static-pages")


def _post_friend_create(request: HttpRequest) -> HttpResponse:
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="friend_create")
    form = forms.friend_new
    if not form.is_valid():
        return _render(request, status=422, forms=forms, page_error="请修正友情链接。")
    try:
        create_friend_link(
            actor_id=request.account_id,
            name=form.cleaned_data["name"],
            url=form.cleaned_data["url"],
            description=form.cleaned_data["description"],
            logo_asset_id=form.cleaned_data["logo_asset_id"],
            position=form.cleaned_data["position"],
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(f"{reverse('admin:site-settings')}?saved=friend#create-friend-link")


def _post_friend_update(request: HttpRequest) -> HttpResponse:
    link_id = request.POST.get("link_id", "")
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="friend_update", identity=link_id)
    form = forms.friend_links.get(link_id)
    if form is None:
        return _render(request, status=422, forms=forms, page_error="友情链接不存在。")
    if not form.is_valid():
        return _render(request, status=422, forms=forms, page_error="请修正友情链接。")
    try:
        update_friend_link(
            actor_id=request.account_id, **form.cleaned_data, **_meta(request)
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(f"{reverse('admin:site-settings')}?saved=friend#friend-links")


def _post_friend_delete(request: HttpRequest) -> HttpResponse:
    link_id = request.POST.get("link_id", "")
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="friend_delete", identity=link_id)
    form = forms.friend_delete.get(link_id)
    if form is None:
        return _render(request, status=422, forms=forms, page_error="友情链接不存在。")
    if not form.is_valid():
        return _render(
            request, status=422, forms=forms, page_error="请重新确认友情链接删除。"
        )
    try:
        delete_friend_link(
            actor_id=request.account_id, **form.cleaned_data, **_meta(request)
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(f"{reverse('admin:site-settings')}?saved=friend#friend-links")


def _post_trusted_source(request: HttpRequest) -> HttpResponse:
    source_key = request.POST.get("source_key", "")
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(
        request, settings=settings, action="trusted_source", identity=source_key
    )
    form = forms.trusted_sources.get(source_key)
    if form is None:
        return _render(request, status=422, forms=forms, page_error="可信来源不存在。")
    if not form.is_valid():
        return _render(
            request, status=422, forms=forms, page_error="请修正可信来源设置。"
        )
    try:
        set_trusted_embed_source(
            actor_id=request.account_id,
            **form.cleaned_data,
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(f"{reverse('admin:site-settings')}?saved=trusted#trusted-sources")


def _post_guestbook(request: HttpRequest) -> HttpResponse:
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="guestbook")
    form = forms.guestbook
    if not form.is_valid():
        return _render(request, status=422, forms=forms, page_error="请修正留言设置。")
    try:
        update_guestbook_settings(
            actor_id=request.account_id,
            **form.cleaned_data,
            **_meta(request),
        )
    except GuestbookSettingsError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(
        f"{reverse('admin:site-settings')}?saved=guestbook#guestbook-settings"
    )


def site_settings(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return _render(request)
    action = request.POST.get("action", "")
    handlers = {
        "configuration": _post_configuration,
        "static_page": _post_static_page,
        "friend_create": _post_friend_create,
        "friend_update": _post_friend_update,
        "friend_delete": _post_friend_delete,
        "trusted_source": _post_trusted_source,
        "guestbook": _post_guestbook,
    }
    handler = handlers.get(action)
    if handler is None:
        return _render(request, status=422, page_error="站点设置操作无效。")
    return handler(request)


__all__ = ["site_settings"]
