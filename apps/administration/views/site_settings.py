import json

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import (
    DEFAULT_VERIFICATION_EMAIL_TEMPLATE,
    render_verification_email_html,
)
from apps.comments.public import GuestbookSettingsError, update_guestbook_settings
from apps.core.http import is_htmx_fragment_request
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
    update_verification_email_template,
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


def _friend_link_entries(settings, forms: SiteSettingsForms):
    return tuple(
        (
            link,
            forms.friend_links[str(link.id)],
            forms.friend_delete[str(link.id)],
        )
        for link in settings.friend_links
    )


def _friend_dialog(settings, forms: SiteSettingsForms, *, kind: str, link_id: str = ""):
    if not kind:
        return None
    if kind == "create":
        return {
            "kind": kind,
            "action": "friend_create",
            "title": "新增友情链接",
            "description": "填写公开显示的站点信息和排序位置。",
            "submit_label": "新增友情链接",
            "return_focus_id": "friend-link-create",
            "return_url": f"{reverse('admin:site-settings')}#friend-links",
            "form": forms.friend_new,
            "link": None,
        }
    if kind not in {"edit", "delete"}:
        raise Http404
    link = next(
        (item for item in settings.friend_links if str(item.id) == link_id),
        None,
    )
    if link is None:
        raise Http404
    if kind == "edit":
        return {
            "kind": kind,
            "action": "friend_update",
            "title": "编辑友情链接",
            "description": f"更新“{link.name}”的公开信息和排序位置。",
            "submit_label": "保存链接",
            "return_focus_id": f"friend-link-edit-{link.id}",
            "return_url": f"{reverse('admin:site-settings')}#friend-links",
            "form": forms.friend_links[link_id],
            "link": link,
        }
    return {
        "kind": kind,
        "action": "friend_delete",
        "title": "删除这个友情链接？",
        "description": "删除后公开页面会立即更新，此操作不能撤销。",
        "submit_label": "删除链接",
        "return_focus_id": f"friend-link-delete-{link.id}",
        "return_url": f"{reverse('admin:site-settings')}#friend-links",
        "form": forms.friend_delete[link_id],
        "link": link,
    }


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    page_error: str = "",
    forms: SiteSettingsForms | None = None,
    friend_dialog_kind: str = "",
    friend_dialog_link_id: str = "",
    template_name: str = "administration/site_settings.html",
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
    try:
        form_bundle = forms or build_site_settings_forms(
            settings,
            actor_id=request.account_id,
        )
    except DatabaseError:
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
    friend_entries = _friend_link_entries(settings, form_bundle)
    dialog = _friend_dialog(
        settings,
        form_bundle,
        kind=friend_dialog_kind,
        link_id=friend_dialog_link_id,
    )
    if template_name == "administration/partials/friend_link_dialog.html":
        response = render(
            request,
            template_name,
            {"friend_dialog": dialog},
            status=status,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    if template_name == "administration/partials/friend_link_manager.html":
        response = render(
            request,
            template_name,
            {"friend_link_entries": friend_entries},
            status=status,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    email_template = (
        settings.configuration.verification_email_template
        or DEFAULT_VERIFICATION_EMAIL_TEMPLATE
    )
    email_preview = render_verification_email_html(
        email_template,
        site_name=settings.configuration.site_name,
        code="123456",
        minutes=10,
        purpose="账号安全验证",
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
            "friend_link_entries": friend_entries,
            "friend_dialog": dialog,
            "trusted_source_entries": tuple(
                (source, form_bundle.trusted_sources[source.source_key])
                for source in settings.trusted_sources
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "verification_email_customized": bool(
                settings.configuration.verification_email_template
            ),
            "verification_email_preview": email_preview,
            "media_upload_urls": {
                "site_logo": reverse("media:upload", kwargs={"adapter": "site-logo"}),
                "site_hero": reverse("media:upload", kwargs={"adapter": "site-hero"}),
            },
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _friend_dialog_error(
    request: HttpRequest,
    *,
    forms: SiteSettingsForms,
    kind: str,
    link_id: str = "",
    status: int = 422,
) -> HttpResponse:
    template_name = (
        "administration/partials/friend_link_dialog.html"
        if is_htmx_fragment_request(request)
        else "administration/site_settings.html"
    )
    response = _render(
        request,
        status=status,
        forms=forms,
        friend_dialog_kind=kind,
        friend_dialog_link_id=link_id,
        template_name=template_name,
    )
    if is_htmx_fragment_request(request):
        response.headers["HX-Retarget"] = "#friend-link-dialog-host"
        response.headers["HX-Reswap"] = "innerHTML"
    return response


def _friend_success(
    request: HttpRequest,
    *,
    message: str,
    focus_id: str,
) -> HttpResponse:
    if not is_htmx_fragment_request(request):
        return redirect(f"{reverse('admin:site-settings')}?saved=friend#friend-links")
    response = _render(
        request,
        template_name="administration/partials/friend_link_manager.html",
    )
    response.headers["HX-Trigger-After-Swap"] = json.dumps(
        {
            "kaj:feedback": {
                "key": "friend-link-saved",
                "level": "success",
                "message": message,
                "timeout": 4500,
            },
            "kaj:focus": {"id": focus_id},
        },
    )
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
        files=request.FILES,
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


def _post_verification_email(request: HttpRequest) -> HttpResponse:
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="verification_email")
    form = forms.verification_email
    if not form.is_valid():
        return _render(
            request,
            status=422,
            forms=forms,
            page_error="请修正验证码邮件模板。",
        )
    try:
        update_verification_email_template(
            actor_id=request.account_id,
            template_source=form.cleaned_data["template_source"],
            expected_version=form.cleaned_data["expected_version"],
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request, status=_status(error), forms=forms, page_error=error.safe_message
        )
    return redirect(f"{reverse('admin:site-settings')}?saved=email#verification-email")


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
        return _friend_dialog_error(request, forms=forms, kind="create")
    try:
        created = create_friend_link(
            actor_id=request.account_id,
            name=form.cleaned_data["name"],
            url=form.cleaned_data["url"],
            description=form.cleaned_data["description"],
            position=form.cleaned_data["position"],
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _friend_dialog_error(
            request,
            forms=forms,
            kind="create",
            status=_status(error),
        )
    return _friend_success(
        request,
        message="友情链接已新增。",
        focus_id=f"friend-link-edit-{created.link_id}",
    )


def _post_friend_update(request: HttpRequest) -> HttpResponse:
    link_id = request.POST.get("link_id", "")
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="friend_update", identity=link_id)
    form = forms.friend_links.get(link_id)
    if form is None:
        return _render(request, status=422, forms=forms, page_error="友情链接不存在。")
    if not form.is_valid():
        return _friend_dialog_error(
            request,
            forms=forms,
            kind="edit",
            link_id=link_id,
        )
    try:
        update_friend_link(
            actor_id=request.account_id, **form.cleaned_data, **_meta(request)
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _friend_dialog_error(
            request,
            forms=forms,
            kind="edit",
            link_id=link_id,
            status=_status(error),
        )
    return _friend_success(
        request,
        message="友情链接已更新。",
        focus_id=f"friend-link-edit-{link_id}",
    )


def _post_friend_delete(request: HttpRequest) -> HttpResponse:
    link_id = request.POST.get("link_id", "")
    settings = admin_site_settings(actor_id=request.account_id)
    forms = _bound(request, settings=settings, action="friend_delete", identity=link_id)
    form = forms.friend_delete.get(link_id)
    if form is None:
        return _render(request, status=422, forms=forms, page_error="友情链接不存在。")
    if not form.is_valid():
        return _friend_dialog_error(
            request,
            forms=forms,
            kind="delete",
            link_id=link_id,
        )
    try:
        delete_friend_link(
            actor_id=request.account_id, **form.cleaned_data, **_meta(request)
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _friend_dialog_error(
            request,
            forms=forms,
            kind="delete",
            link_id=link_id,
            status=_status(error),
        )
    return _friend_success(
        request,
        message="友情链接已删除。",
        focus_id="friend-link-create",
    )


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
        if request.GET.get("focus") == "article-explanation-settings":
            return redirect(reverse("admin:article-explanation-settings"))
        friend_dialog_kind = request.GET.get("friend_dialog", "")
        friend_dialog_link_id = request.GET.get("link_id", "")
        template_name = (
            "administration/partials/friend_link_dialog.html"
            if friend_dialog_kind and is_htmx_fragment_request(request)
            else "administration/site_settings.html"
        )
        return _render(
            request,
            friend_dialog_kind=friend_dialog_kind,
            friend_dialog_link_id=friend_dialog_link_id,
            template_name=template_name,
        )
    action = request.POST.get("action", "")
    handlers = {
        "configuration": _post_configuration,
        "verification_email": _post_verification_email,
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
