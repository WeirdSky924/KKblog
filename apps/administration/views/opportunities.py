import json
from urllib.parse import urlencode

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.administration.forms.opportunities import (
    CheckActionForm,
    OpportunityCreateForm,
    OpportunityEditForm,
    OpportunityFilterForm,
    OpportunityPageForm,
    OpportunitySettingsForm,
    ReviewBatchForm,
    ReviewDecisionForm,
    SourceFilterForm,
    SourceForm,
)
from apps.administration.presentation.opportunity_attention import (
    OPPORTUNITY_CHECK_RUN_TARGET,
    opportunity_attention_counts,
)
from apps.notifications.public import (
    mark_target_notifications_read,
    unread_notification_count,
)
from apps.opportunities.public import (
    OpportunityAdministrationDraft,
    OpportunityCommandError,
    OpportunityDraft,
    OpportunityFilterKind,
    SourceDraft,
    activate_source_and_request_check,
    admin_adapter_choices,
    admin_check_run_source_detail,
    admin_check_run_sources,
    admin_filter_options,
    admin_opportunities,
    admin_opportunity_detail,
    admin_review_queue,
    admin_settings,
    admin_source_choices,
    admin_source_detail,
    admin_sources,
    create_opportunity,
    create_source,
    disable_source,
    dispatch_check_run,
    public_opportunity_filters,
    request_check_cancellation,
    request_full_check,
    request_source_check,
    resolve_review_item,
    resolve_review_items,
    update_opportunity,
    update_opportunity_settings,
    update_source,
)

TABS = ("reviews", "jobs", "sources", "runs", "settings")


def _meta(request):
    return {
        "actor_id": request.account_id,
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
    }


def _tab(request):
    value = request.GET.get("tab", "reviews")
    if value not in TABS:
        raise Http404
    return value


def _filters(actor_id):
    return {
        "category_ids": tuple(
            (row.id, row.label)
            for row in admin_filter_options(
                actor_id=actor_id, kind=OpportunityFilterKind.CATEGORY
            )
        ),
        "city_ids": tuple(
            (row.id, row.label)
            for row in admin_filter_options(
                actor_id=actor_id, kind=OpportunityFilterKind.CITY
            )
        ),
        "cohort_ids": tuple(
            (row.id, row.label)
            for row in admin_filter_options(
                actor_id=actor_id, kind=OpportunityFilterKind.COHORT
            )
        ),
    }


def _source_form(actor_id, *, data=None, detail=None):
    initial = None
    if detail is not None:
        initial = {
            "source_id": detail.item.source_id,
            "company_name": detail.item.company_name,
            "source_type": detail.item.source_type,
            "official_url": detail.item.official_url,
            "note": detail.note,
            "adapter_key": detail.item.adapter_key,
            "allowed_hosts": "\n".join(detail.allowed_hosts),
            "respect_robots_txt": detail.respect_robots_txt,
            "request_interval_seconds": detail.request_interval_seconds,
            "max_pages": detail.max_pages,
            "max_opportunities": detail.max_opportunities,
            "max_duration_seconds": detail.max_duration_seconds,
        }
    return SourceForm(
        data,
        initial=initial,
        adapter_choices=admin_adapter_choices(actor_id=actor_id),
    )


def _opportunity_form(actor_id, *, data=None, detail=None, edit=False):
    filter_choices = _filters(actor_id)
    source_choices = admin_source_choices(actor_id=actor_id)
    initial = None
    if detail is not None:
        initial = {
            "opportunity_id": detail.item.opportunity_id,
            "source_id": detail.item.source_id,
            "title": detail.item.title,
            "target_url": detail.item.target_url,
            "recruitment_type": detail.item.recruitment_type,
            "plan": detail.item.plan,
            "location_text": detail.item.location_text,
            "public_evidence": detail.public_evidence,
            "category_ids": detail.category_ids,
            "city_ids": detail.city_ids,
            "cohort_ids": detail.cohort_ids,
            "verification_status": detail.item.verification_status,
            "publication_state": detail.item.publication_state,
        }
    form_class = OpportunityEditForm if edit else OpportunityCreateForm
    return form_class(
        data,
        initial=initial,
        source_choices=source_choices,
        filter_choices=filter_choices,
    )


def _dialog(request, tab):
    kind = request.GET.get("dialog", "")
    if not kind:
        return "", None, None
    actor_id = request.account_id
    if kind == "source-create":
        return kind, _source_form(actor_id), None
    if kind == "source-edit":
        detail = admin_source_detail(
            actor_id=actor_id, source_id=request.GET.get("source_id", "")
        )
        if detail is None:
            raise Http404
        return kind, _source_form(actor_id, detail=detail), None
    if kind == "job-create":
        return kind, _opportunity_form(actor_id), None
    if kind == "job-edit":
        detail = admin_opportunity_detail(
            actor_id=actor_id, opportunity_id=request.GET.get("opportunity_id", "")
        )
        if detail is None:
            raise Http404
        return kind, _opportunity_form(actor_id, detail=detail, edit=True), None
    if kind == "run-detail" and tab == "runs":
        detail = admin_check_run_source_detail(
            actor_id=actor_id,
            source_run_id=request.GET.get("source_run_id", ""),
        )
        if detail is None:
            raise Http404
        return kind, None, detail
    raise Http404


def _dialog_return_url(request):
    query = request.GET.copy()
    dialog_kind = query.get("dialog", "")
    query.pop("dialog", None)
    query.pop("confirm", None)
    query.pop("saved", None)
    query.pop("count", None)
    if dialog_kind == "source-edit":
        query.pop("source_id", None)
    elif dialog_kind == "job-edit":
        query.pop("opportunity_id", None)
    elif dialog_kind == "run-detail":
        query.pop("source_run_id", None)
    encoded = query.urlencode()
    base = reverse("admin:opportunities")
    return f"{base}?{encoded}" if encoded else base


def _dialog_return_focus_id(request, dialog_kind):
    if dialog_kind == "source-create":
        return "source-create-trigger"
    if dialog_kind == "job-create":
        return "job-create-trigger"
    if dialog_kind == "source-edit":
        identity = request.GET.get("source_id") or request.POST.get("source_id", "")
        return f"source-edit-{identity}" if identity else ""
    if dialog_kind == "job-edit":
        identity = request.GET.get("opportunity_id") or request.POST.get(
            "opportunity_id", ""
        )
        return f"job-edit-{identity}" if identity else ""
    if dialog_kind == "run-detail":
        identity = request.GET.get("source_run_id", "")
        return f"run-detail-{identity}" if identity else ""
    return ""


def _form_query(request, form, *, include_page, tab=None):
    pairs = [("tab", tab or _tab(request))]
    for name in form.fields:
        if name == "page" and not include_page:
            continue
        pairs.extend(
            (name, value)
            for value in request.GET.getlist(name)
            if value not in (None, "")
        )
    return urlencode(pairs)


def _pagination_query(request, form, *, tab=None):
    return _form_query(request, form, include_page=False, tab=tab)


def _list_query(request, form, *, tab=None):
    return _form_query(request, form, include_page=True, tab=tab)


def _settings_form(actor_id, *, data=None):
    filters = public_opportunity_filters()
    current = admin_settings(actor_id=actor_id)
    return OpportunitySettingsForm(
        data,
        initial={
            "default_city_ids": current.default_city_ids,
            "default_verification_statuses": current.default_verification_statuses,
            "default_source_ids": current.default_source_ids,
            "default_recruitment_types": current.default_recruitment_types,
            "default_category_ids": current.default_category_ids,
            "default_cohort_ids": current.default_cohort_ids,
        },
        source_choices=tuple(
            (str(item.source_id), item.label) for item in filters.sources
        ),
        filter_choices={
            "default_city_ids": tuple(
                (item.option_id, item.label) for item in filters.cities
            ),
            "default_category_ids": tuple(
                (item.option_id, item.label) for item in filters.categories
            ),
            "default_cohort_ids": tuple(
                (item.option_id, item.label) for item in filters.cohorts
            ),
        },
    )


def _render(
    request,
    *,
    status=200,
    active_tab=None,
    dialog_kind="",
    dialog_form=None,
    run_detail=None,
    settings_form=None,
    page_error="",
):
    tab = active_tab or _tab(request)
    actor_id = request.account_id
    context = {
        "active_tab": tab,
        "opportunity_tabs": TABS,
        "dialog_kind": dialog_kind,
        "dialog_form": dialog_form,
        "dialog_return_url": _dialog_return_url(request),
        "dialog_return_focus_id": _dialog_return_focus_id(request, dialog_kind),
        "run_detail": run_detail,
        "run_detail_return_url": _dialog_return_url(request),
        "list_query": urlencode({"tab": tab}),
        "pagination_query": urlencode({"tab": tab}),
        "page_error": page_error,
        "saved": request.GET.get("saved", ""),
        "saved_count": 0,
    }
    try:
        context["saved_count"] = max(0, int(request.GET.get("count", "0")))
    except (TypeError, ValueError):
        pass
    if tab == "reviews":
        form = OpportunityPageForm(request.GET)
        context["pagination_query"] = _pagination_query(request, form, tab=tab)
        context["list_query"] = _list_query(request, form, tab=tab)
        if form.is_valid():
            review_page = admin_review_queue(
                actor_id=actor_id,
                page=form.cleaned_data.get("page") or 1,
                page_size=form.cleaned_data.get("per_page") or 20,
            )
            context["review_page"] = review_page
            context["review_batch_all_form"] = ReviewBatchForm(
                initial={
                    "scope": "ALL",
                    "page": review_page.page,
                    "per_page": review_page.page_size,
                }
            )
            context["review_all_confirm"] = (
                request.GET.get("confirm", "") == "review-all"
            )
            context["review_all_description"] = (
                f"将接受并确认当前全部待审核项，共计 {review_page.total} 项。"
            )
            context["review_all_return_url"] = _dialog_return_url(request)
        else:
            status = 422
        context["page_form"] = form
    elif tab == "jobs":
        choices = _filters(actor_id)
        form = OpportunityFilterForm(
            request.GET,
            source_choices=admin_source_choices(actor_id=actor_id),
            filter_choices=choices,
        )
        context["pagination_query"] = _pagination_query(request, form, tab=tab)
        context["list_query"] = _list_query(request, form, tab=tab)
        if form.is_valid():
            values = form.cleaned_data
            context["job_page"] = admin_opportunities(
                actor_id=actor_id,
                query=values["q"],
                verification_status=values["verification_status"],
                publication_state=values["publication_state"],
                source_id=values["source_id"],
                recruitment_type=values["recruitment_type"],
                origin=values["origin"],
                category_ids=values["category_ids"],
                city_ids=values["city_ids"],
                cohort_ids=values["cohort_ids"],
                list_missing=values["list_missing"],
                page=values.get("page") or 1,
                page_size=values.get("per_page") or 20,
            )
        else:
            status = 422
        context["job_filter_form"] = form
    elif tab == "sources":
        form = SourceFilterForm(request.GET)
        context["pagination_query"] = _pagination_query(request, form, tab=tab)
        context["list_query"] = _list_query(request, form, tab=tab)
        if form.is_valid():
            values = form.cleaned_data
            context["source_page"] = admin_sources(
                actor_id=actor_id,
                query=values["q"],
                enabled=values["enabled"],
                source_type=values["source_type"],
                check_state=values["check_state"],
                page=values.get("page") or 1,
                page_size=values.get("per_page") or 20,
            )
        else:
            status = 422
        context["source_filter_form"] = form
    elif tab == "runs":
        form = OpportunityPageForm(request.GET)
        context["pagination_query"] = _pagination_query(request, form, tab=tab)
        context["list_query"] = _list_query(request, form, tab=tab)
        if form.is_valid():
            context["run_page"] = admin_check_run_sources(
                actor_id=actor_id,
                page=form.cleaned_data.get("page") or 1,
                page_size=form.cleaned_data.get("per_page") or 20,
            )
        else:
            status = 422
        context["page_form"] = form
    else:
        context["settings_form"] = settings_form or _settings_form(actor_id)
    response = render(
        request, "administration/opportunities.html", context, status=status
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _redirect(tab, saved, **params):
    query = urlencode({"tab": tab, "saved": saved, **params})
    return redirect(f"{reverse('admin:opportunities')}?{query}")


def _service_error(request, *, tab, form, error):
    form.add_error(None, error.safe_message)
    return _render(
        request,
        status=409 if "busy" in error.code or "conflict" in error.code else 422,
        active_tab=tab,
        dialog_kind=request.POST.get("dialog_kind", ""),
        dialog_form=form,
        settings_form=form if tab == "settings" else None,
    )


def _throttled(request, action):
    key = f"opp-admin:{request.account_id}:{action}"
    try:
        return not cache.add(key, "1", timeout=2)
    except Exception:
        return False


def _post(request):
    action = request.POST.get("action", "")
    meta = _meta(request)
    if action == "mark_runs_read":
        mark_target_notifications_read(
            recipient_id=request.account_id,
            target_type=OPPORTUNITY_CHECK_RUN_TARGET,
        )
        review_count, _unread_run_count = opportunity_attention_counts(
            actor_id=request.account_id
        )
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=204)
            response.headers["HX-Trigger"] = json.dumps(
                {
                    "kaj:administration-attention-read": {
                        "key": "opportunities",
                        "count": review_count,
                        "notificationUnreadCount": unread_notification_count(
                            recipient_id=request.account_id
                        ),
                    }
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
            return response
        return _redirect("runs", "read")
    if action in {"source_create", "source_edit"}:
        form = _source_form(request.account_id, data=request.POST)
        if not form.is_valid():
            return _render(
                request,
                status=422,
                active_tab="sources",
                dialog_kind=action.replace("_", "-"),
                dialog_form=form,
            )
        values = form.cleaned_data
        draft = SourceDraft(
            company_name=values["company_name"],
            source_type=values["source_type"],
            official_url=values["official_url"],
            note=values["note"],
            adapter_key=values["adapter_key"],
            respect_robots_txt=values["respect_robots_txt"],
            request_interval_seconds=values["request_interval_seconds"],
            max_pages=values["max_pages"],
            max_opportunities=values["max_opportunities"],
            max_duration_seconds=values["max_duration_seconds"],
            allowed_hosts=values["allowed_hosts"],
        )
        try:
            if action == "source_create":
                create_source(draft=draft, **meta)
            else:
                update_source(source_id=values["source_id"], draft=draft, **meta)
        except OpportunityCommandError as error:
            return _service_error(request, tab="sources", form=form, error=error)
        return _redirect("sources", "source")
    if action in {"job_create", "job_edit"}:
        edit = action == "job_edit"
        form = _opportunity_form(request.account_id, data=request.POST, edit=edit)
        if not form.is_valid():
            return _render(
                request,
                status=422,
                active_tab="jobs",
                dialog_kind=action.replace("_", "-"),
                dialog_form=form,
            )
        values = form.cleaned_data
        try:
            if edit:
                draft = OpportunityAdministrationDraft(
                    title=values["title"],
                    target_url=values["target_url"],
                    recruitment_type=values["recruitment_type"],
                    plan=values["plan"],
                    location_text=values["location_text"],
                    public_evidence=values["public_evidence"],
                    category_ids=tuple(values["category_ids"]),
                    city_ids=tuple(values["city_ids"]),
                    cohort_ids=tuple(values["cohort_ids"]),
                    verification_status=values["verification_status"],
                    publication_state=values["publication_state"],
                )
                update_opportunity(
                    opportunity_id=values["opportunity_id"], draft=draft, **meta
                )
            else:
                draft = OpportunityDraft(
                    source_id=values["source_id"],
                    title=values["title"],
                    target_url=values["target_url"],
                    recruitment_type=values["recruitment_type"],
                    plan=values["plan"],
                    location_text=values["location_text"],
                    public_evidence=values["public_evidence"],
                    category_ids=tuple(values["category_ids"]),
                    city_ids=tuple(values["city_ids"]),
                    cohort_ids=tuple(values["cohort_ids"]),
                )
                create_opportunity(draft=draft, **meta)
        except OpportunityCommandError as error:
            return _service_error(request, tab="jobs", form=form, error=error)
        return _redirect("jobs", "job")
    if action == "review_resolve":
        form = ReviewDecisionForm(request.POST)
        if not form.is_valid():
            return _render(
                request, status=422, active_tab="reviews", page_error="审核请求不完整。"
            )
        try:
            resolve_review_item(
                review_id=form.cleaned_data["review_id"],
                decision=form.cleaned_data["decision"],
                **meta,
            )
        except OpportunityCommandError as error:
            return _service_error(request, tab="reviews", form=form, error=error)
        return _redirect("reviews", "review")
    if action == "review_resolve_batch":
        form = ReviewBatchForm(request.POST)
        if not form.is_valid():
            return _render(
                request,
                status=422,
                active_tab="reviews",
                page_error="批量审核请求不完整。",
            )
        if _throttled(request, "review_resolve_batch"):
            return _render(
                request,
                status=429,
                active_tab="reviews",
                page_error="操作过于频繁，请稍后再试。",
            )
        scope = form.cleaned_data["scope"]
        try:
            result = resolve_review_items(
                review_ids=(
                    form.cleaned_data["review_ids"] if scope == "PAGE" else None
                ),
                decision="ACCEPTED",
                **meta,
            )
        except OpportunityCommandError as error:
            return _render(
                request,
                status=422,
                active_tab="reviews",
                page_error=error.safe_message,
            )
        params = {"count": result.resolved_count}
        if scope == "PAGE":
            params.update(
                {
                    "page": form.cleaned_data.get("page") or 1,
                    "per_page": form.cleaned_data.get("per_page") or 20,
                }
            )
        return _redirect(
            "reviews",
            "review-page" if scope == "PAGE" else "review-all",
            **params,
        )
    if action == "settings_update":
        form = _settings_form(request.account_id, data=request.POST)
        if not form.is_valid():
            return _render(
                request,
                status=422,
                active_tab="settings",
                settings_form=form,
                page_error="请检查默认筛选设置。",
            )
        try:
            update_opportunity_settings(
                city_ids=tuple(form.cleaned_data["default_city_ids"]),
                verification_statuses=tuple(
                    form.cleaned_data["default_verification_statuses"]
                ),
                source_ids=tuple(form.cleaned_data["default_source_ids"]),
                recruitment_types=tuple(form.cleaned_data["default_recruitment_types"]),
                category_ids=tuple(form.cleaned_data["default_category_ids"]),
                cohort_ids=tuple(form.cleaned_data["default_cohort_ids"]),
                **meta,
            )
        except OpportunityCommandError as error:
            return _service_error(request, tab="settings", form=form, error=error)
        return _redirect("settings", "settings")
    if action in {
        "source_disable",
        "source_enable",
        "source_check",
        "retry_source_check",
        "check_all",
        "cancel_run",
    }:
        form = CheckActionForm(request.POST)
        tab = (
            "runs"
            if action in {"retry_source_check", "check_all", "cancel_run"}
            else "sources"
        )
        if not form.is_valid():
            return _render(
                request, status=422, active_tab=tab, page_error="检查请求不完整。"
            )
        if _throttled(request, action):
            return _render(
                request,
                status=429,
                active_tab=tab,
                page_error="操作过于频繁，请稍后再试。",
            )
        try:
            if action == "source_disable":
                disable_source(source_id=form.cleaned_data["source_id"], **meta)
            elif action == "source_enable":
                activate_source_and_request_check(
                    source_id=form.cleaned_data["source_id"],
                    dispatcher=dispatch_check_run,
                    **meta,
                )
            elif action in {"source_check", "retry_source_check"}:
                request_source_check(
                    source_id=form.cleaned_data["source_id"],
                    dispatcher=dispatch_check_run,
                    **meta,
                )
            elif action == "check_all":
                request_full_check(dispatcher=dispatch_check_run, **meta)
            else:
                cancellation = request_check_cancellation(
                    run_id=form.cleaned_data["run_id"], **meta
                )
        except OpportunityCommandError as error:
            return _service_error(request, tab=tab, form=form, error=error)
        if action == "cancel_run":
            saved = (
                "check-cancelled"
                if cancellation.state == "CANCELLED"
                else "check-cancel-requested"
            )
            return _redirect(tab, saved)
        return _redirect(tab, "check")
    raise Http404


def opportunities(request: HttpRequest) -> HttpResponse:
    try:
        if request.method == "POST":
            return _post(request)
        tab = _tab(request)
        dialog_kind, dialog_form, run_detail = _dialog(request, tab)
        return _render(
            request,
            active_tab=tab,
            dialog_kind=dialog_kind,
            dialog_form=dialog_form,
            run_detail=run_detail,
        )
    except PermissionError:
        raise PermissionDenied from None


__all__ = ["opportunities"]
