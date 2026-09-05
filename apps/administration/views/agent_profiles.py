from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.accounts.public import is_administrator
from apps.administration.forms.agents import (
    AgentProfileForm,
    AgentPromptForm,
    AgentPromptSwitchForm,
)
from apps.agents.public import (
    AgentCommandError,
    agent_endpoint_admin_items,
    agent_profile_admin_items,
    agent_profile_prompt_admin_detail,
    agents_schema_ready,
    create_agent_profile,
    save_agent_prompt_revision,
    switch_agent_prompt_revision,
    update_agent_profile,
)
from apps.media.public import RenderingError, render_markdown


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
    }


def _profile(items, profile_id):
    return next((item for item in items if str(item.profile_id) == profile_id), None)


def _profile_initial(item) -> dict[str, object]:
    return {
        "profile_id": item.profile_id,
        "expected_version": item.row_version,
        "key": item.key,
        "display_name": item.display_name,
        "purpose": item.purpose,
        "endpoint_id": item.endpoint_id,
        "schema_key": item.schema_key,
        "enabled": item.enabled,
    }


def _profile_form(*, endpoints, data=None, initial=None, key_readonly=False):
    return AgentProfileForm(
        data,
        initial=initial,
        endpoints=endpoints,
        key_readonly=key_readonly,
    )


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _detail(request, profile_id, *, revision_id=None):
    try:
        return agent_profile_prompt_admin_detail(
            actor_id=request.account_id,
            profile_id=profile_id,
            page=_page_number(request.GET.get("prompt_page")),
            page_size=20,
            revision_id=revision_id,
        )
    except LookupError:
        raise Http404 from None


def _dialog_from_query(request, profiles, endpoints):
    kind = request.GET.get("dialog", "")
    profile_id = request.GET.get("profile_id", "")
    item = _profile(profiles, profile_id) if profile_id else None
    if not kind:
        return "", None, None, None
    if kind == "profile-create":
        return kind, None, _profile_form(endpoints=endpoints), None
    if item is None:
        raise Http404
    if kind == "profile-edit":
        return (
            kind,
            item,
            _profile_form(
                endpoints=endpoints,
                initial=_profile_initial(item),
                key_readonly=True,
            ),
            None,
        )
    detail = _detail(
        request,
        item.profile_id,
        revision_id=request.GET.get("revision_id") if kind == "prompt-switch" else None,
    )
    if kind == "prompt-edit":
        current_source = next(
            (row.markdown_source for row in detail.revisions if row.is_current), ""
        )
        form = AgentPromptForm(
            initial={
                "profile_id": item.profile_id,
                "expected_version": item.row_version,
                "markdown_source": current_source,
            }
        )
        return kind, item, form, detail
    if kind == "prompt-switch":
        revision_id = request.GET.get("revision_id", "")
        revision = next(
            (row for row in detail.revisions if str(row.revision_id) == revision_id),
            None,
        )
        if revision is None or revision.is_current:
            raise Http404
        form = AgentPromptSwitchForm(
            initial={
                "profile_id": item.profile_id,
                "revision_id": revision.revision_id,
                "expected_version": item.row_version,
                "confirm": "prompt_switch",
            }
        )
        return kind, item, form, detail
    raise Http404


def _render(
    request: HttpRequest,
    *,
    status=200,
    dialog_kind="",
    dialog_profile=None,
    dialog_form=None,
    prompt_detail=None,
    prompt_preview_html="",
    page_error="",
) -> HttpResponse:
    if not agents_schema_ready():
        return render(
            request,
            "administration/agent_profiles.html",
            {"schema_unavailable": True},
            status=503,
        )
    endpoints = agent_endpoint_admin_items(actor_id=request.account_id)
    profiles = agent_profile_admin_items(actor_id=request.account_id)
    if not dialog_kind and dialog_form is None:
        dialog_kind, dialog_profile, dialog_form, prompt_detail = _dialog_from_query(
            request, profiles, endpoints
        )
    response = render(
        request,
        "administration/agent_profiles.html",
        {
            "profile_items": profiles,
            "endpoint_items": endpoints,
            "dialog_kind": dialog_kind,
            "dialog_profile": dialog_profile,
            "dialog_form": dialog_form,
            "prompt_detail": prompt_detail,
            "prompt_pagination_query": (
                urlencode(
                    {
                        "dialog": "prompt-edit",
                        "profile_id": prompt_detail.profile.profile_id,
                    }
                )
                if prompt_detail is not None
                else ""
            ),
            "prompt_preview_html": prompt_preview_html,
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _save_profile(request, *, create: bool):
    endpoints = agent_endpoint_admin_items(actor_id=request.account_id)
    item = None
    if not create:
        item = _profile(
            agent_profile_admin_items(actor_id=request.account_id),
            request.POST.get("profile_id", ""),
        )
        if item is None:
            raise Http404
    form = _profile_form(
        endpoints=endpoints,
        data=request.POST,
        initial=_profile_initial(item) if item is not None else None,
        key_readonly=not create,
    )
    if not form.is_valid():
        return _render(
            request,
            status=422,
            dialog_kind="profile-create" if create else "profile-edit",
            dialog_profile=item,
            dialog_form=form,
        )
    try:
        if create:
            create_agent_profile(
                actor_id=request.account_id,
                draft=form.draft(),
                **_meta(request),
            )
        else:
            update_agent_profile(
                actor_id=request.account_id,
                profile_id=form.cleaned_data["profile_id"],
                draft=form.draft(),
                expected_version=form.cleaned_data["expected_version"],
                **_meta(request),
            )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        return _render(
            request,
            status=409 if error.code == "agents.configuration_conflict.v1" else 422,
            dialog_kind="profile-create" if create else "profile-edit",
            dialog_profile=item,
            dialog_form=form,
        )
    saved = "profile-created" if create else "profile-updated"
    return redirect(f"{reverse('admin:agent-profiles')}?saved={saved}#profile-list")


def _prompt_action(request, *, preview: bool):
    form = AgentPromptForm(request.POST)
    detail = _detail(request, request.POST.get("profile_id", ""))
    if not form.is_valid():
        return _render(
            request,
            status=422,
            dialog_kind="prompt-edit",
            dialog_profile=detail.profile,
            dialog_form=form,
            prompt_detail=detail,
        )
    if preview:
        try:
            preview_html = render_markdown(form.cleaned_data["markdown_source"]).html
        except (RenderingError, TypeError, ValueError):
            form.add_error("markdown_source", "Prompt 无法安全预览。")
            preview_html = ""
        return _render(
            request,
            status=422 if form.errors else 200,
            dialog_kind="prompt-edit",
            dialog_profile=detail.profile,
            dialog_form=form,
            prompt_detail=detail,
            prompt_preview_html=preview_html,
        )
    try:
        save_agent_prompt_revision(
            actor_id=request.account_id,
            profile_id=form.cleaned_data["profile_id"],
            markdown_source=form.cleaned_data["markdown_source"],
            expected_profile_version=form.cleaned_data["expected_version"],
            **_meta(request),
        )
    except AgentCommandError as error:
        form.add_error("markdown_source", str(error))
        return _render(
            request,
            status=409 if error.code == "agents.configuration_conflict.v1" else 422,
            dialog_kind="prompt-edit",
            dialog_profile=detail.profile,
            dialog_form=form,
            prompt_detail=detail,
        )
    return redirect(
        f"{reverse('admin:agent-profiles')}?saved=prompt-saved#profile-list"
    )


def _switch_prompt(request):
    form = AgentPromptSwitchForm(request.POST)
    if not form.is_valid():
        message = "请重新确认 Prompt 版本切换。"
        form.add_error(None, message)
        profile_id = form.cleaned_data.get("profile_id")
        if profile_id is None:
            return _render(request, status=422, page_error=message)
        detail = _detail(request, profile_id)
        return _render(
            request,
            status=422,
            dialog_kind="prompt-switch",
            dialog_profile=detail.profile,
            dialog_form=form,
            prompt_detail=detail,
        )
    try:
        switch_agent_prompt_revision(
            actor_id=request.account_id,
            profile_id=form.cleaned_data["profile_id"],
            prompt_revision_id=form.cleaned_data["revision_id"],
            expected_version=form.cleaned_data["expected_version"],
            **_meta(request),
        )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        detail = _detail(request, form.cleaned_data["profile_id"])
        return _render(
            request,
            status=409,
            dialog_kind="prompt-switch",
            dialog_profile=detail.profile,
            dialog_form=form,
            prompt_detail=detail,
        )
    return redirect(
        f"{reverse('admin:agent-profiles')}?saved=prompt-switched#profile-list"
    )


def agent_profiles(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "GET":
        return _render(request)
    action = request.POST.get("action", "")
    if action == "profile_create":
        return _save_profile(request, create=True)
    if action == "profile_update":
        return _save_profile(request, create=False)
    if action == "prompt_preview":
        return _prompt_action(request, preview=True)
    if action == "prompt_save":
        return _prompt_action(request, preview=False)
    if action == "prompt_switch":
        return _switch_prompt(request)
    raise Http404
