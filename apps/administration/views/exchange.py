from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_GET

from apps.accounts.public import admin_author_choices, is_administrator
from apps.administration.forms.operations import (
    ExportCancellationForm,
    ExportRequestForm,
)
from apps.content.public import admin_article_page, admin_section_page
from apps.exchange.public import (
    ExportLifecycleError,
    ExportRequestError,
    export_job_detail,
    export_job_records,
)
from apps.operations.public import backup_records
from config.exchange_integrations import (
    cancel_configured_export,
    configured_export_download,
    open_configured_export_archive,
    request_configured_export,
)


def _choice_context(actor_id):
    authors = admin_author_choices(actor_id=actor_id)
    sections = admin_section_page(actor_id=actor_id)
    articles = admin_article_page(actor_id=actor_id, limit=500)
    return {
        "author_choices": tuple(
            (str(item.account_id), f"{item.display_name} · {item.email}")
            for item in authors
        ),
        "section_choices": tuple((str(item.id), item.name) for item in sections),
        "article_choices": tuple((item.id, item.title) for item in articles),
        "author_labels": {str(item.account_id): item.display_name for item in authors},
        "section_labels": {str(item.id): item.name for item in sections},
        "article_labels": {item.id: item.title for item in articles},
    }


def _request_form(actor_id, data=None):
    choices = _choice_context(actor_id)
    form = ExportRequestForm(
        data,
        author_choices=choices["author_choices"],
        section_choices=choices["section_choices"],
        article_choices=choices["article_choices"],
    )
    return form, choices


def _metadata(request: HttpRequest) -> dict[str, str]:
    return {
        "actor_id": request.account_id,
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
    }


def _scope_label(job, choices) -> str:
    if job.scope == "ALL":
        return "全站"
    if job.scope == "AUTHOR":
        return choices["author_labels"].get(str(job.scope_author_id), "已移除作者")
    if job.scope == "SECTION":
        return choices["section_labels"].get(str(job.scope_section_id), "已移除分区")
    titles = [
        choices["article_labels"].get(article_id, "已移除文章")
        for article_id in job.requested_article_ids
    ]
    if len(titles) == 1:
        return titles[0]
    return f"{len(titles)} 篇文章"


def _render(
    request: HttpRequest,
    *,
    request_form=None,
    choices=None,
    cancellation_form=None,
    confirmation_job_id="",
    page_error="",
    status=200,
) -> HttpResponse:
    if request_form is None or choices is None:
        request_form, choices = _request_form(request.account_id)
    try:
        page_number = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page_number = 1
        page_error = page_error or "分页条件无效。"
        status = 422
    export_page = export_job_records(
        actor_id=request.account_id,
        is_admin=True,
        page=page_number,
        page_size=20,
    )
    jobs = tuple(
        {"item": item, "scope_label": _scope_label(item, choices)}
        for item in export_page.items
    )
    try:
        backup_page_number = max(1, int(request.GET.get("backup_page", "1")))
    except (TypeError, ValueError):
        backup_page_number = 1
        page_error = page_error or "备份分页条件无效。"
        status = 422
    backup_page = backup_records(
        is_admin=True,
        page=backup_page_number,
        page_size=20,
    )
    confirm_id = confirmation_job_id or request.GET.get("confirm", "").strip()
    confirmation_job = None
    if confirm_id:
        try:
            confirmation_job = export_job_detail(
                actor_id=request.account_id,
                job_id=confirm_id,
                is_admin=True,
            )
        except LookupError:
            raise Http404 from None
        if not confirmation_job.can_cancel:
            raise Http404
        cancellation_form = cancellation_form or ExportCancellationForm(
            initial={"job_id": confirmation_job.job_id, "confirm": "cancel"}
        )
    return render(
        request,
        "administration/exchange.html",
        {
            "export_request_form": request_form,
            "export_jobs": jobs,
            "export_page": export_page,
            "pagination_query": urlencode(
                {"backup_page": request.GET.get("backup_page")}
            )
            if request.GET.get("backup_page")
            else "",
            "backup_rows": backup_page.items,
            "backup_page": backup_page,
            "backup_pagination_query": urlencode({"page": request.GET.get("page")})
            if request.GET.get("page")
            else "",
            "export_confirmation_job": confirmation_job,
            "export_cancellation_form": cancellation_form,
            "author_labels": choices["author_labels"],
            "section_labels": choices["section_labels"],
            "article_labels": choices["article_labels"],
            "saved": request.GET.get("saved", ""),
            "page_error": page_error,
        },
        status=status,
    )


def exchange(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "GET":
        return _render(request)

    action = request.POST.get("action", "")
    if action == "request":
        form, choices = _request_form(request.account_id, request.POST)
        if not form.is_valid():
            return _render(request, request_form=form, choices=choices, status=422)
        try:
            result = request_configured_export(
                scope=form.cleaned_data["scope"],
                scope_author_id=form.cleaned_data["scope_author_id"] or None,
                scope_section_id=form.cleaned_data["scope_section_id"] or None,
                article_ids=tuple(form.cleaned_data["article_ids"]),
                **_metadata(request),
            )
        except ExportRequestError as exc:
            form.add_error(None, exc.safe_message)
            response_status = 409 if exc.code == "exchange.export_running.v1" else 422
            return _render(
                request,
                request_form=form,
                choices=choices,
                status=response_status,
            )
        return redirect(
            f"{reverse('admin:exchange')}?saved=requested#export-{result.job_id}"
        )

    if action == "cancel":
        form = ExportCancellationForm(request.POST)
        if not form.is_valid():
            return _render(
                request,
                cancellation_form=form,
                confirmation_job_id=request.POST.get("job_id", ""),
                status=422,
            )
        try:
            result = cancel_configured_export(
                job_id=form.cleaned_data["job_id"],
                **_metadata(request),
            )
        except ExportLifecycleError as exc:
            if exc.code == "exchange.export_not_found.v1":
                raise Http404 from None
            form.add_error(None, exc.safe_message)
            response_status = (
                503 if exc.code == "exchange.export_cancel_cleanup_failed.v1" else 409
            )
            return _render(
                request,
                cancellation_form=form,
                confirmation_job_id=form.cleaned_data["job_id"],
                status=response_status,
            )
        return redirect(
            f"{reverse('admin:exchange')}?saved=cancelled#export-{result.job_id}"
        )

    form, choices = _request_form(request.account_id, request.POST)
    form.add_error(None, "请选择有效的交换操作。")
    return _render(request, request_form=form, choices=choices, status=422)


@require_GET
def download_export(request: HttpRequest, job_id: str) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    try:
        grant = configured_export_download(job_id=job_id, **_metadata(request))
    except ExportLifecycleError as exc:
        if exc.code == "exchange.export_not_found.v1":
            raise Http404 from None
        return _render(request, page_error=exc.safe_message, status=409)
    response = FileResponse(
        open_configured_export_archive(grant),
        as_attachment=True,
        filename=grant.download_name,
        content_type=grant.content_type,
    )
    response.headers["Content-Length"] = str(grant.size_bytes)
    return response


__all__ = ["download_export", "exchange"]
