from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import admin_account_detail, is_administrator
from apps.learning.public import (
    LearningCommandError,
    admin_learning_account_quota_override,
    admin_learning_quota_snapshot,
    configure_account_quota_override,
    configure_question_bank_api,
    configure_site_quota_policy,
    question_bank_api_configuration,
    reset_daily_generation_usage,
)

from ..forms.learning import (
    LearningAccountQuotaForm,
    LearningGenerationResetForm,
    LearningQuestionBankApiForm,
    LearningQuotaForm,
)
from .learning_documents import _meta


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    page_error: str = "",
    site_form=None,
    account_form=None,
    account=None,
    saved: str = "",
    api_form=None,
    generation_reset_form=None,
) -> HttpResponse:
    quota = admin_learning_quota_snapshot(actor_id=request.account_id)
    api_configuration = question_bank_api_configuration()
    response = render(
        request,
        "administration/learning_question_banks.html",
        {
            "quota": quota,
            "site_form": site_form
            or LearningQuotaForm(
                initial={
                    "daily_uploads": quota.site.daily_uploads,
                    "pending_reviews": quota.site.pending_reviews,
                    "daily_generations": quota.site.daily_generations,
                    "concurrent_model_runs": quota.site.concurrent_model_runs,
                    "unpurged_banks": quota.site.unpurged_banks,
                    "max_questions_per_volume": quota.site.max_questions_per_volume,
                    "expected_version": quota.site.row_version,
                }
            ),
            "account": account,
            "account_form": account_form,
            "api_configuration": api_configuration,
            "api_form": api_form
            or LearningQuestionBankApiForm(
                initial={
                    "enabled": api_configuration.enabled,
                    "cors_mode": api_configuration.cors_mode,
                    "cors_origins": "\n".join(api_configuration.cors_origins),
                    "minute_limit": api_configuration.minute_limit,
                    "daily_limit": api_configuration.daily_limit,
                    "expected_version": api_configuration.row_version,
                }
            ),
            "generation_reset_form": generation_reset_form,
            "page_error": page_error,
            "saved": saved or request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def learning_question_banks(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "GET":
        if request.GET.get("dialog") == "learning-generation-reset":
            return _render(
                request,
                generation_reset_form=LearningGenerationResetForm(
                    initial={"confirm": "learning_generation_reset"}
                ),
            )
        account = None
        account_form = None
        account_id = request.GET.get("account_id", "")
        if account_id:
            try:
                account = admin_account_detail(
                    actor_id=request.account_id,
                    account_id=account_id,
                )
                override = admin_learning_account_quota_override(
                    actor_id=request.account_id,
                    account_id=account.account_id,
                )
            except (LearningCommandError, ValueError):
                raise Http404 from None
            account_form = LearningAccountQuotaForm(
                initial={
                    "account_id": account.account_id,
                    "expected_version": override.row_version if override else 0,
                    "daily_uploads": override.daily_uploads if override else None,
                    "pending_reviews": override.pending_reviews if override else None,
                    "daily_generations": override.daily_generations
                    if override
                    else None,
                    "concurrent_model_runs": override.concurrent_model_runs
                    if override
                    else None,
                    "unpurged_banks": override.unpurged_banks if override else None,
                }
            )
        return _render(request, account=account, account_form=account_form)
    return _post(request)


def _post(request: HttpRequest) -> HttpResponse:
    action_values = request.POST.getlist("action")
    command = request.POST.get("command") or (
        "learning_batch_execute"
        if "learning_batch_execute" in action_values
        else request.POST.get("action", "")
    )
    if command == "learning_batch_execute":
        return redirect(reverse("admin:question-bank-queue"))
    if command == "learning_question_bank_api":
        form = LearningQuestionBankApiForm(request.POST)
        if not form.is_valid():
            return _render(request, status=422, api_form=form)
        try:
            configure_question_bank_api(
                actor_id=request.account_id,
                enabled=form.cleaned_data["enabled"],
                cors_mode=form.cleaned_data["cors_mode"],
                cors_origins=form.cleaned_data["cors_origins"],
                minute_limit=form.cleaned_data["minute_limit"],
                daily_limit=form.cleaned_data["daily_limit"],
                expected_version=form.cleaned_data["expected_version"],
                **_meta(request),
            )
        except LearningCommandError as error:
            form.add_error(None, error.safe_message)
            return _render(request, status=409, api_form=form)
        return redirect(f"{reverse('admin:question-banks')}?saved=api")
    if command == "learning_site_quota":
        form = LearningQuotaForm(request.POST)
        if not form.is_valid():
            return _render(request, status=422, site_form=form)
        try:
            configure_site_quota_policy(
                actor_id=request.account_id,
                expected_version=form.cleaned_data["expected_version"],
                limits=form.limits(),
                max_questions_per_volume=form.cleaned_data.get(
                    "max_questions_per_volume"
                ),
                **_meta(request),
            )
        except LearningCommandError as error:
            form.add_error(None, error.safe_message)
            return _render(request, status=409, site_form=form)
        return redirect(f"{reverse('admin:question-banks')}?saved=quota")
    if command == "learning_generation_reset":
        form = LearningGenerationResetForm(request.POST)
        if not form.is_valid():
            return _render(request, status=422, generation_reset_form=form)
        try:
            reset_daily_generation_usage(
                actor_id=request.account_id,
                **_meta(request),
            )
        except LearningCommandError as error:
            form.add_error(None, error.safe_message)
            return _render(request, status=409, generation_reset_form=form)
        return redirect(f"{reverse('admin:question-banks')}?saved=generation-reset")
    if command == "learning_account_quota":
        form = LearningAccountQuotaForm(request.POST)
        if not form.is_valid():
            return _render(request, status=422, account_form=form)
        try:
            configure_account_quota_override(
                actor_id=request.account_id,
                account_id=form.cleaned_data["account_id"],
                expected_version=form.cleaned_data["expected_version"],
                limits=form.limits(),
                **_meta(request),
            )
        except LearningCommandError as error:
            form.add_error(None, error.safe_message)
            return _render(request, status=409, account_form=form)
        return redirect(
            f"{reverse('admin:question-banks')}?saved=account-quota"
            f"&account_id={form.cleaned_data['account_id']}"
        )
    raise Http404


__all__ = ["learning_question_banks"]
