from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.core.http import is_htmx_fragment_request
from apps.learning.public import (
    LearningAdminTargetType,
    LearningCommandError,
    admin_question_bank_page,
    execute_learning_admin_batch,
    preflight_learning_admin_batch,
)

from ..forms.learning import LearningQuestionBankFilterForm
from .learning_documents import _batch_form, _filter_query, _meta


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    page_error: str = "",
    batch_preview=None,
    batch_form=None,
    saved: str = "",
) -> HttpResponse:
    filter_form = LearningQuestionBankFilterForm(request.GET or None)
    if filter_form.is_valid():
        cleaned = filter_form.cleaned_data
        page = admin_question_bank_page(
            actor_id=request.account_id,
            keyword=cleaned.get("q", ""),
            state=cleaned.get("state", ""),
            visibility=cleaned.get("visibility", ""),
            page=cleaned.get("page") or 1,
            page_size=20,
        )
    else:
        page = admin_question_bank_page(actor_id=request.account_id)
        if request.GET:
            status = 422
    template_name = (
        "administration/partials/learning_question_bank_queue.html"
        if is_htmx_fragment_request(request) and batch_preview is None
        else "administration/learning_question_bank_queue.html"
    )
    response = render(
        request,
        template_name,
        {
            "bank_page": page,
            "filter_form": filter_form,
            "filter_query": _filter_query(request),
            "batch_preview": batch_preview,
            "batch_form": batch_form,
            "page_error": page_error,
            "saved": saved or request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def learning_question_bank_queue(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "GET":
        selected = request.GET.getlist("selected")
        action = request.GET.get("batch_action", "")
        if action and selected:
            form = _batch_form(
                request,
                target_values=selected,
                data={
                    "target_type": LearningAdminTargetType.QUESTION_BANK,
                    "action": action,
                    "targets": selected,
                    "confirm": "learning_batch",
                },
            )
            if form.is_valid():
                try:
                    preview = preflight_learning_admin_batch(
                        administrator_id=request.account_id,
                        target_type=form.cleaned_data["target_type"],
                        action=form.cleaned_data["action"],
                        targets=form.cleaned_data["targets"],
                    )
                except LearningCommandError as error:
                    return _render(request, status=422, page_error=error.safe_message)
                form.data = form.data.copy()
                form.data["confirm"] = ""
                return _render(request, batch_preview=preview, batch_form=form)
            return _render(request, status=422, batch_form=form)
        return _render(request)
    return _post(request)


def _post(request: HttpRequest) -> HttpResponse:
    action_values = request.POST.getlist("action")
    command = request.POST.get("command") or (
        "learning_batch_execute"
        if "learning_batch_execute" in action_values
        else request.POST.get("action", "")
    )
    if command != "learning_batch_execute":
        raise PermissionDenied
    values = request.POST.getlist("targets")
    form_data = request.POST.copy()
    if len(action_values) > 1:
        form_data["action"] = action_values[-1]
    elif request.POST.get("batch_action"):
        form_data["action"] = request.POST["batch_action"]
    form = _batch_form(
        request,
        target_values=values,
        data=form_data,
        require_reason=form_data.get("action") in {"HIDE", "DELETE"},
    )
    if not values:
        return _render(
            request,
            status=422,
            page_error="没有收到已勾选的题库，请返回队列后重新选择。",
            batch_form=form,
        )
    if not form.is_valid():
        return _render(request, status=422, batch_form=form)
    try:
        result = execute_learning_admin_batch(
            administrator_id=request.account_id,
            target_type=form.cleaned_data["target_type"],
            action=form.cleaned_data["action"],
            targets=form.cleaned_data["targets"],
            reason_code=form.cleaned_data.get("reason_code", ""),
            **_meta(request),
        )
    except LearningCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(request, status=422, batch_form=form)
    if result.total < 1:
        return _render(
            request,
            status=422,
            page_error="本次没有执行任何题库，请重新选择后再试。",
            batch_form=form,
        )
    params = {
        "saved": "batch",
        "total": result.total,
        "succeeded": result.succeeded,
        "failed": result.failed,
    }
    if result.failed:
        failure = next(item for item in result.items if not item.succeeded)
        params["error"] = failure.safe_message or failure.error_code
    return redirect(f"{reverse('admin:question-bank-queue')}?{urlencode(params)}")


__all__ = ["learning_question_bank_queue"]
