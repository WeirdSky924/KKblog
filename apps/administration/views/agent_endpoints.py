import json

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.administration.forms.agents import (
    AgentEndpointCheckForm,
    AgentEndpointForm,
    AgentRestoreDefaultsForm,
    AgentSiteTokenLimitForm,
    AgentTokenResetForm,
)
from apps.agents.public import (
    AgentCommandError,
    agent_endpoint_admin_items,
    agent_endpoint_capability_options,
    agent_token_policy_admin_item,
    agents_schema_ready,
    create_agent_endpoint,
    request_agent_endpoint_check,
    reset_token_usage,
    restore_default_token_limits,
    update_agent_endpoint,
    update_site_daily_token_limit,
)
from apps.agents.tasks import dispatch_endpoint_check
from apps.core.ids import new_ulid


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
    }


def _endpoint(items, endpoint_id):
    return next((item for item in items if str(item.endpoint_id) == endpoint_id), None)


def _endpoint_initial(item) -> dict[str, object]:
    return {
        "endpoint_id": item.endpoint_id,
        "expected_version": item.row_version,
        "display_name": item.display_name,
        "protocol": item.protocol,
        "base_url": item.base_url,
        "model_name": item.model_name,
        "authentication_mode": item.authentication_mode,
        "secret_alias": item.secret_alias,
        "api_key": "",
        "clear_api_key": False,
        "enabled": item.enabled,
        "context_window_tokens": item.context_window_tokens,
        "max_output_tokens": item.max_output_tokens,
        "reasoning_effort": item.reasoning_effort,
        "thinking_budget_tokens": item.thinking_budget_tokens,
        "per_run_token_limit": item.per_run_token_limit,
        "request_timeout_seconds": item.request_timeout_seconds,
        "concurrency_limit": item.concurrency_limit,
        "endpoint_daily_token_limit": item.daily_token_limit,
        "input_price_per_million_tokens": item.input_price_per_million_tokens,
        "output_price_per_million_tokens": item.output_price_per_million_tokens,
    }


def _endpoint_form(*, policy, data=None, initial=None):
    aliases = tuple(sorted(settings.AGENT_PROVIDER_ENVIRONMENT.secrets))
    return AgentEndpointForm(
        data,
        initial=initial,
        site_daily_limit=policy.site_daily_token_limit,
        secret_aliases=aliases,
    )


def _dialog_from_query(request, items, policy):
    kind = request.GET.get("dialog", "")
    endpoint_id = request.GET.get("endpoint_id", "")
    item = _endpoint(items, endpoint_id) if endpoint_id else None
    if not kind:
        return "", None, None
    if kind == "endpoint-create":
        return kind, None, _endpoint_form(policy=policy)
    if kind == "token-reset-site":
        return (
            kind,
            None,
            AgentTokenResetForm(
                initial={
                    "scope": "SITE",
                    "endpoint_id": "",
                    "expected_ledger_version": policy.site_ledger_version,
                    "operation_id": new_ulid(),
                    "confirm": "token_reset",
                }
            ),
        )
    if kind == "restore-defaults":
        return (
            kind,
            None,
            AgentRestoreDefaultsForm(
                initial={
                    "expected_site_version": policy.site_row_version,
                    "endpoint_versions": json.dumps(
                        {
                            str(endpoint_id): row_version
                            for endpoint_id, _limit, row_version in policy.endpoint_limits
                        }
                    ),
                    "confirm": "restore_defaults",
                }
            ),
        )
    if item is None:
        raise Http404
    if kind == "endpoint-edit":
        return (
            kind,
            item,
            _endpoint_form(policy=policy, initial=_endpoint_initial(item)),
        )
    if kind == "endpoint-check":
        capability_options = agent_endpoint_capability_options(
            actor_id=request.account_id,
            endpoint_id=item.endpoint_id,
        )
        return (
            kind,
            item,
            AgentEndpointCheckForm(
                capability_options=capability_options,
                initial={
                    "endpoint_id": item.endpoint_id,
                    "expected_version": item.row_version,
                    "request_id": new_ulid(),
                    "confirm": "endpoint_check",
                },
            ),
        )
    if kind == "token-reset-endpoint":
        return (
            kind,
            item,
            AgentTokenResetForm(
                initial={
                    "scope": "ENDPOINT",
                    "endpoint_id": item.endpoint_id,
                    "expected_ledger_version": item.today_ledger_version,
                    "operation_id": new_ulid(),
                    "confirm": "token_reset",
                }
            ),
        )
    raise Http404


def _render(
    request: HttpRequest,
    *,
    status=200,
    dialog_kind="",
    dialog_endpoint=None,
    dialog_form=None,
    site_form=None,
    page_error="",
) -> HttpResponse:
    if not agents_schema_ready():
        return render(
            request,
            "administration/agent_endpoints.html",
            {"schema_unavailable": True},
            status=503,
        )
    items = agent_endpoint_admin_items(actor_id=request.account_id)
    policy = agent_token_policy_admin_item(actor_id=request.account_id)
    if not dialog_kind and dialog_form is None:
        dialog_kind, dialog_endpoint, dialog_form = _dialog_from_query(
            request, items, policy
        )
    response = render(
        request,
        "administration/agent_endpoints.html",
        {
            "endpoint_items": items,
            "token_policy": policy,
            "site_form": site_form
            or AgentSiteTokenLimitForm(
                initial={
                    "daily_token_limit": policy.site_daily_token_limit,
                    "expected_version": policy.site_row_version,
                }
            ),
            "dialog_kind": dialog_kind,
            "dialog_endpoint": dialog_endpoint,
            "dialog_form": dialog_form,
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "agent_secret_count": len(settings.AGENT_PROVIDER_ENVIRONMENT.secrets),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _save_endpoint(request, *, create: bool):
    policy = agent_token_policy_admin_item(actor_id=request.account_id)
    form = _endpoint_form(policy=policy, data=request.POST)
    item = None
    if not create:
        item = _endpoint(
            agent_endpoint_admin_items(actor_id=request.account_id),
            request.POST.get("endpoint_id", ""),
        )
        if item is None:
            raise Http404
    if not form.is_valid():
        return _render(
            request,
            status=422,
            dialog_kind="endpoint-create" if create else "endpoint-edit",
            dialog_endpoint=item,
            dialog_form=form,
        )
    try:
        if create:
            create_agent_endpoint(
                actor_id=request.account_id,
                draft=form.draft(),
                **_meta(request),
            )
        else:
            update_agent_endpoint(
                actor_id=request.account_id,
                endpoint_id=form.cleaned_data["endpoint_id"],
                draft=form.draft(),
                expected_version=form.cleaned_data["expected_version"],
                **_meta(request),
            )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        return _render(
            request,
            status=409 if error.code == "agents.configuration_conflict.v1" else 422,
            dialog_kind="endpoint-create" if create else "endpoint-edit",
            dialog_endpoint=item,
            dialog_form=form,
        )
    saved = "endpoint-created" if create else "endpoint-updated"
    return redirect(f"{reverse('admin:agent-endpoints')}?saved={saved}#endpoint-list")


def _update_site_limit(request):
    form = AgentSiteTokenLimitForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, site_form=form)
    try:
        update_site_daily_token_limit(
            actor_id=request.account_id,
            daily_token_limit=form.cleaned_data["daily_token_limit"],
            expected_version=form.cleaned_data["expected_version"],
            **_meta(request),
        )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        return _render(
            request,
            status=409 if error.code == "agents.configuration_conflict.v1" else 422,
            site_form=form,
        )
    return redirect(f"{reverse('admin:agent-endpoints')}?saved=site-limit")


def _request_check(request):
    endpoint_item = _endpoint(
        agent_endpoint_admin_items(actor_id=request.account_id),
        request.POST.get("endpoint_id", ""),
    )
    capability_options = (
        agent_endpoint_capability_options(
            actor_id=request.account_id,
            endpoint_id=endpoint_item.endpoint_id,
        )
        if endpoint_item is not None
        else ()
    )
    form = AgentEndpointCheckForm(
        request.POST,
        capability_options=capability_options,
    )
    if not form.is_valid():
        item = endpoint_item
        if item is None:
            return _render(request, status=422, page_error="请重新确认连接检查。")
        return _render(
            request,
            status=422,
            dialog_kind="endpoint-check",
            dialog_endpoint=item,
            dialog_form=form,
        )
    try:
        request_agent_endpoint_check(
            actor_id=request.account_id,
            endpoint_id=form.cleaned_data["endpoint_id"],
            expected_endpoint_version=form.cleaned_data["expected_version"],
            idempotency_key=form.cleaned_data["request_id"],
            dispatcher=dispatch_endpoint_check,
            profile_key=form.cleaned_data.get("profile_key", ""),
            **_meta(request),
        )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        return _render(
            request,
            status=409 if error.code == "agents.configuration_conflict.v1" else 422,
            dialog_kind="endpoint-check",
            dialog_endpoint=_endpoint(
                agent_endpoint_admin_items(actor_id=request.account_id),
                str(form.cleaned_data.get("endpoint_id", "")),
            ),
            dialog_form=form,
        )
    return redirect(f"{reverse('admin:agent-endpoints')}?saved=check-requested")


def _reset_usage(request):
    form = AgentTokenResetForm(request.POST)
    item = _endpoint(
        agent_endpoint_admin_items(actor_id=request.account_id),
        request.POST.get("endpoint_id", ""),
    )
    if not form.is_valid():
        return _render(
            request,
            status=422,
            dialog_kind="token-reset",
            dialog_endpoint=item,
            dialog_form=form,
        )
    try:
        reset_token_usage(
            actor_id=request.account_id,
            scope=form.cleaned_data["scope"],
            endpoint_id=form.cleaned_data["endpoint_id"],
            reason=form.cleaned_data["reason"],
            idempotency_key=form.cleaned_data["operation_id"],
            expected_ledger_version=form.cleaned_data["expected_ledger_version"],
            **_meta(request),
        )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        return _render(
            request,
            status=409 if error.code == "agents.configuration_conflict.v1" else 422,
            dialog_kind="token-reset",
            dialog_endpoint=item,
            dialog_form=form,
        )
    return redirect(f"{reverse('admin:agent-endpoints')}?saved=usage-reset")


def _restore_defaults(request):
    form = AgentRestoreDefaultsForm(request.POST)
    if not form.is_valid():
        return _render(
            request,
            status=422,
            dialog_kind="restore-defaults",
            dialog_form=form,
        )
    try:
        restore_default_token_limits(
            actor_id=request.account_id,
            expected_site_version=form.cleaned_data["expected_site_version"],
            expected_endpoint_versions=form.cleaned_data["endpoint_versions"],
            **_meta(request),
        )
    except AgentCommandError as error:
        form.add_error(None, str(error))
        return _render(
            request, status=409, dialog_kind="restore-defaults", dialog_form=form
        )
    return redirect(f"{reverse('admin:agent-endpoints')}?saved=defaults-restored")


def agent_endpoints(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "GET":
        return _render(request)
    handlers = {
        "endpoint_create": lambda: _save_endpoint(request, create=True),
        "endpoint_update": lambda: _save_endpoint(request, create=False),
        "site_limit_update": lambda: _update_site_limit(request),
        "endpoint_check": lambda: _request_check(request),
        "token_reset": lambda: _reset_usage(request),
        "restore_defaults": lambda: _restore_defaults(request),
    }
    handler = handlers.get(request.POST.get("action", ""))
    if handler is None:
        raise Http404
    return handler()
