from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.accounts.public import (
    AccountAdministrationQueryError,
    InviteError,
    generate_invite_codes,
    invite_detail,
    invite_list,
    is_administrator,
    revoke_invites,
)
from apps.administration.forms.invites import (
    InviteGenerationForm,
    InviteRevocationConfirmationForm,
    InviteRevocationForm,
)
from apps.operations.public import record_audit_entry


def _active_choices():
    return [
        (row.id, row.display_suffix) for row in invite_list(state="ACTIVE", limit=1000)
    ]


def _page(value) -> int:
    try:
        return max(1, int(value or "1"))
    except (TypeError, ValueError):
        return 1


def _detail(request: HttpRequest):
    invite_id = request.GET.get("detail", "")
    if not invite_id:
        return None
    try:
        detail = invite_detail(invite_id=invite_id, actor_id=request.account_id)
    except AccountAdministrationQueryError:
        raise Http404 from None
    except PermissionError:
        raise PermissionDenied from None
    if detail.redeemed_account is None:
        raise Http404
    return detail


def _render(
    request: HttpRequest,
    *,
    generation_form=None,
    revoke_form=None,
    revoke_confirmation=None,
    confirmation_count=0,
    confirmation_focus_id="",
    issued=(),
    error="",
    status=200,
) -> HttpResponse:
    state = request.GET.get("state", "")
    try:
        invite_page = invite_list(
            state=state, page=_page(request.GET.get("page")), page_size=20
        )
    except ValueError:
        invite_page = invite_list(state="", page=1, page_size=20)
        error = "筛选条件无效。"
        status = 422
    choices = _active_choices()
    if revoke_confirmation is None:
        confirm_id = request.GET.get("confirm", "")
        if confirm_id:
            choice = next((item for item in choices if item[0] == confirm_id), None)
            if choice is None:
                raise Http404
            revoke_confirmation = InviteRevocationConfirmationForm(
                invite_choices=(choice,),
                initial={"invite_ids": [confirm_id], "confirm": "revoke"},
            )
            confirmation_count = 1
            confirmation_focus_id = f"invite-revoke-{confirm_id}"
    detail = _detail(request)
    response = render(
        request,
        "administration/invites.html",
        {
            "rows": invite_page.items,
            "invite_page": invite_page,
            "pagination_query": urlencode({"state": state}),
            "detail": detail,
            "issued": issued,
            "error": error,
            "saved": request.GET.get("saved", ""),
            "generation_form": generation_form or InviteGenerationForm(),
            "revoke_form": revoke_form or InviteRevocationForm(invite_choices=choices),
            "has_revoke_choices": bool(choices),
            "revoke_confirmation": revoke_confirmation,
            "revocation_dialog_open": revoke_confirmation is not None,
            "revocation_title": (
                "确认撤销这个邀请码？"
                if confirmation_count == 1
                else f"确认批量撤销 {confirmation_count} 个邀请码？"
            ),
            "confirmation_focus_id": confirmation_focus_id,
            "revocation_return_url": (
                f"{reverse('admin:invites')}#invite-history-title"
            ),
            "selected_state": state,
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _meta(request: HttpRequest) -> dict[str, object]:
    return {
        "actor_id": request.account_id,
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
        "audit_writer": record_audit_entry,
    }


def invites(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "GET":
        return _render(request)

    action = request.POST.get("action", "")
    if action == "generate":
        form = InviteGenerationForm(request.POST)
        if not form.is_valid():
            return _render(request, generation_form=form, status=422)
        try:
            issued = generate_invite_codes(
                count=form.cleaned_data["count"],
                validity_days=form.cleaned_data["validity_days"],
                **_meta(request),
            )
        except InviteError as exc:
            form.add_error(None, str(exc))
            return _render(request, generation_form=form, status=422)
        except PermissionError:
            raise PermissionDenied from None
        return _render(request, issued=issued)

    choices = _active_choices()
    if action == "preview_revoke":
        form = InviteRevocationForm(request.POST, invite_choices=choices)
        if not form.is_valid():
            return _render(request, revoke_form=form, status=422)
        selected = form.cleaned_data["invite_ids"]
        confirmation = InviteRevocationConfirmationForm(
            invite_choices=choices,
            initial={"invite_ids": selected, "confirm": "revoke"},
        )
        return _render(
            request,
            revoke_form=form,
            revoke_confirmation=confirmation,
            confirmation_count=len(selected),
            confirmation_focus_id="invite-revoke-selected",
        )

    form = InviteRevocationConfirmationForm(request.POST, invite_choices=choices)
    if action != "revoke" or not form.is_valid():
        if action != "revoke":
            form.add_error(None, "邀请码管理操作无效。")
        return _render(
            request,
            revoke_confirmation=form,
            confirmation_count=len(request.POST.getlist("invite_ids")),
            confirmation_focus_id="invite-revoke-selected",
            status=422,
        )
    try:
        revoke_invites(invite_ids=form.cleaned_data["invite_ids"], **_meta(request))
    except InviteError as exc:
        form.add_error(None, str(exc))
        return _render(
            request,
            revoke_confirmation=form,
            confirmation_count=len(form.cleaned_data["invite_ids"]),
            confirmation_focus_id="invite-revoke-selected",
            status=422,
        )
    except PermissionError:
        raise PermissionDenied from None
    return redirect(f"{reverse('admin:invites')}?saved=revoked")


__all__ = ["invites"]
