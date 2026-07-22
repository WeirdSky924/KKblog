from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import (
    block_ip,
    ip_block_detail,
    ip_block_list,
    is_administrator,
    unblock_ip,
)
from apps.accounts.services.ip_blocks import IpBlockError
from apps.administration.forms.ip_blocks import (
    IpBlockConfirmationForm,
    IpBlockForm,
    IpUnblockConfirmationForm,
)
from apps.operations.public import record_audit_entry


def _detail(block_id: str):
    if not block_id:
        return None
    try:
        return ip_block_detail(block_id=block_id, is_admin=True)
    except (ObjectDoesNotExist, ValidationError):
        raise Http404 from None


def _render(
    request: HttpRequest,
    *,
    block_form=None,
    block_confirmation=None,
    unblock_confirmation=None,
    confirm_block=False,
    status=200,
) -> HttpResponse:
    keyword = request.GET.get("q", "")
    rows = ip_block_list(is_admin=True, keyword=keyword)
    detail = _detail(request.GET.get("detail", ""))
    confirm_unblock = _detail(request.GET.get("confirm", ""))
    if confirm_unblock is not None and confirm_unblock.unblocked_at is not None:
        raise Http404
    response = render(
        request,
        "administration/ip_blocks.html",
        {
            "rows": rows,
            "keyword": keyword,
            "detail": detail,
            "block_form": block_form or IpBlockForm(),
            "block_confirmation": block_confirmation
            or IpBlockConfirmationForm(
                initial={"address": "", "note": "", "confirm": "block"}
            ),
            "unblock_confirmation": unblock_confirmation
            or IpUnblockConfirmationForm(
                initial={
                    "block_id": confirm_unblock.id if confirm_unblock else "",
                    "confirm": "unblock",
                }
            ),
            "confirm_block": confirm_block,
            "confirm_unblock": confirm_unblock,
            "unblock_dialog_open": bool(
                confirm_unblock or (unblock_confirmation is not None and status == 422)
            ),
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def ip_blocks(request: HttpRequest) -> HttpResponse:
    actor_id = getattr(request, "account_id", None)
    if not is_administrator(actor_id):
        raise PermissionDenied
    if request.method == "GET":
        return _render(request)
    client_ip = request.client_ip
    trace_code = getattr(request, "trace_code", "")
    action = request.POST.get("action", "")
    if action == "preview_block":
        form = IpBlockForm(request.POST)
        if not form.is_valid():
            return _render(request, block_form=form, status=422)
        confirmation = IpBlockConfirmationForm(
            initial={
                "address": form.cleaned_data["address"],
                "note": form.cleaned_data["note"],
                "confirm": "block",
            }
        )
        return _render(
            request,
            block_form=form,
            block_confirmation=confirmation,
            confirm_block=True,
        )
    if action == "block":
        form = IpBlockConfirmationForm(request.POST)
        if form.is_valid():
            try:
                block_ip(
                    address=form.cleaned_data["address"],
                    note=form.cleaned_data["note"],
                    actor_id=actor_id,
                    client_ip=client_ip,
                    trace_code=trace_code,
                    audit_writer=record_audit_entry,
                )
            except IpBlockError as exc:
                form.add_error(None, str(exc))
            else:
                return redirect(f"{reverse('admin:ip-blocks')}?saved=blocked")
        return _render(
            request,
            block_form=IpBlockForm(
                initial={
                    "address": request.POST.get("address", ""),
                    "note": request.POST.get("note", ""),
                }
            ),
            block_confirmation=form,
            confirm_block=True,
            status=422,
        )
    form = IpUnblockConfirmationForm(request.POST)
    if action == "unblock" and form.is_valid():
        try:
            unblock_ip(
                block_id=form.cleaned_data["block_id"],
                actor_id=actor_id,
                client_ip=client_ip,
                trace_code=trace_code,
                audit_writer=record_audit_entry,
            )
        except IpBlockError as exc:
            form.add_error(None, str(exc))
        else:
            return redirect(f"{reverse('admin:ip-blocks')}?saved=unblocked")
    else:
        form.add_error(None, "请确认要解除的封禁记录。")
    return _render(request, unblock_confirmation=form, status=422)
