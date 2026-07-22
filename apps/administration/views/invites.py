from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts.public import is_administrator
from apps.accounts.queries.invites import invite_list
from apps.accounts.services.invites import (
    InviteError,
    generate_invite_codes,
    revoke_invites,
)
from apps.administration.forms.invites import (
    InviteGenerationForm,
    InviteRevocationForm,
)
from apps.operations.public import record_audit_entry


def _render(
    request,
    *,
    generation_form=None,
    revoke_form=None,
    issued=(),
    error="",
    status=200,
):
    state = request.GET.get("state", "")
    try:
        rows = invite_list(state=state)
    except ValueError:
        rows = []
        error = "筛选条件无效。"
        status = 422
    choices = [(row.id, row.display_suffix) for row in rows if row.state == "ACTIVE"]
    response = render(
        request,
        "administration/invites.html",
        {
            "rows": rows,
            "issued": issued,
            "error": error,
            "generation_form": generation_form or InviteGenerationForm(),
            "revoke_form": revoke_form or InviteRevocationForm(invite_choices=choices),
            "selected_state": state,
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def invites(request: HttpRequest) -> HttpResponse:
    actor_id = getattr(request, "account_id", None)
    if not is_administrator(actor_id):
        raise PermissionDenied
    trace_code = getattr(request, "trace_code", "")
    client_ip = getattr(
        request, "client_ip", request.META.get("REMOTE_ADDR", "127.0.0.1")
    )
    if request.method == "GET":
        return _render(request)
    action = request.POST.get("action")
    if action == "generate":
        form = InviteGenerationForm(request.POST)
        if not form.is_valid():
            return _render(request, generation_form=form, status=422)
        try:
            issued = generate_invite_codes(
                count=form.cleaned_data["count"],
                validity_days=form.cleaned_data["validity_days"],
                actor_id=actor_id,
                trace_code=trace_code,
                client_ip=client_ip,
                audit_writer=record_audit_entry,
            )
        except InviteError as exc:
            form.add_error(None, str(exc))
            return _render(request, generation_form=form, status=422)
        return _render(request, issued=issued)
    current_rows = invite_list()
    choices = [
        (row.id, row.display_suffix) for row in current_rows if row.state == "ACTIVE"
    ]
    form = InviteRevocationForm(request.POST, invite_choices=choices)
    if action != "revoke" or not form.is_valid():
        return _render(request, revoke_form=form, status=422)
    try:
        revoke_invites(
            invite_ids=form.cleaned_data["invite_ids"],
            actor_id=actor_id,
            trace_code=trace_code,
            client_ip=client_ip,
            audit_writer=record_audit_entry,
        )
    except InviteError as exc:
        form.add_error(None, str(exc))
        return _render(request, revoke_form=form, status=422)
    return _render(request)
