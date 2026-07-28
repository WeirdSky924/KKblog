from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.authoring.operation_forms import (
    ImportConfirmForm,
    ImportDecisionForm,
    ImportUploadForm,
)
from apps.authoring.presenters import import_workspace_page
from apps.content.public import section_list, selectable_tag_list
from apps.exchange.public import (
    ImportConfirmationError,
    ImportDecisionError,
    ImportPreviewError,
)

from .access import author_id_or_response, private_response


def _method(request, allowed):
    if request.method not in allowed:
        return private_response(HttpResponseNotAllowed(allowed))
    return None


def _integrations():
    from config import exchange_integrations

    return exchange_integrations


def _decision_form(item, *, data=None, preview_version=None):
    initial = {
        "expected_preview_version": preview_version,
        "included": item.included,
        "decision": item.decision,
        "section_id": item.mapped_section_id,
        "tag_ids": item.mapped_tag_ids,
        "proposed_tag_names": ", ".join(item.proposed_tag_names),
    }
    return ImportDecisionForm(
        data,
        prefix=f"item-{item.item_id}",
        initial=initial,
        sections=section_list(),
        tags=selectable_tag_list(),
        allowed_decisions=item.allowed_decisions,
    )


def _context(
    *,
    actor_id,
    job_id: str,
    bound_item_id: str = "",
    bound_form=None,
    error: str = "",
):
    try:
        source = _integrations().configured_import_preview(
            actor_id=actor_id,
            job_id=job_id,
        )
    except ImportDecisionError:
        raise Http404 from None
    page = import_workspace_page(source)
    rows = []
    selected_count = 0
    for item in page.items:
        if item.included and item.decision in {"CREATE", "UPDATE"}:
            selected_count += 1
        form = None
        if page.editable and item.allowed_decisions:
            form = (
                bound_form
                if item.item_id == bound_item_id and bound_form is not None
                else _decision_form(item, preview_version=page.preview_version)
            )
        rows.append({"item": item, "form": form})
    return {
        "import_page": page,
        "import_rows": rows,
        "import_selected_count": selected_count,
        "import_confirm_form": ImportConfirmForm(
            initial={"expected_preview_version": page.preview_version}
        ),
        "import_error": error,
    }


def _render_import(request, *, status=200, template="authoring/import.html", **context):
    return private_response(render(request, template, context, status=status))


def import_workspace(request):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET", "POST")):
        return denied
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["source"]
        try:
            result = _integrations().create_configured_import_preview(
                actor_id=actor_id,
                source_name=upload.name,
                source_kind=upload.source_kind,
                chunks=upload.chunks(),
            )
        except ImportPreviewError as exc:
            form.add_error("source", exc.safe_message)
        else:
            return private_response(
                redirect(
                    reverse(
                        "authoring:import-job",
                        kwargs={"job_id": result.job_id},
                    )
                )
            )
    status = 422 if request.method == "POST" else 200
    return _render_import(
        request,
        status=status,
        import_upload_form=form,
        import_page=None,
    )


def import_job(request, job_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET",)):
        return denied
    return _render_import(
        request,
        import_upload_form=ImportUploadForm(),
        import_updated=request.GET.get("updated") == "1",
        import_confirmed=request.GET.get("confirmed") == "1",
        **_context(actor_id=actor_id, job_id=job_id),
    )


def update_import_item(request, job_id: str, item_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("POST",)):
        return denied
    context = _context(actor_id=actor_id, job_id=job_id)
    page = context["import_page"]
    item = next(
        (candidate for candidate in page.items if candidate.item_id == item_id),
        None,
    )
    if item is None or not page.editable or not item.allowed_decisions:
        raise Http404
    form = _decision_form(
        item,
        data=request.POST,
        preview_version=page.preview_version,
    )
    if not form.is_valid():
        context = _context(
            actor_id=actor_id,
            job_id=job_id,
            bound_item_id=item_id,
            bound_form=form,
        )
        return _render_import(
            request,
            status=422,
            import_upload_form=ImportUploadForm(),
            **context,
        )
    try:
        _integrations().update_configured_import_decision(
            actor_id=actor_id,
            job_id=job_id,
            item_id=item_id,
            expected_preview_version=form.cleaned_data["expected_preview_version"],
            included=form.cleaned_data["included"],
            decision=form.cleaned_data["decision"],
            section_id=form.cleaned_data["section_id"] or None,
            tag_ids=form.cleaned_data["tag_ids"],
            proposed_tag_names=form.cleaned_data["proposed_tag_names"],
            trace_code=request.trace_code,
            client_ip=request.client_ip,
        )
    except ImportDecisionError as exc:
        if exc.code in {
            "exchange.import_not_found.v1",
            "exchange.import_item_not_found.v1",
        }:
            raise Http404 from None
        fresh = _context(actor_id=actor_id, job_id=job_id)
        current = fresh["import_page"]
        current_item = next(
            (candidate for candidate in current.items if candidate.item_id == item_id),
            None,
        )
        if current_item is None or not current_item.allowed_decisions:
            raise Http404 from None
        retry_data = request.POST.copy()
        retry_data["expected_preview_version"] = current.preview_version
        retry_form = _decision_form(current_item, data=retry_data)
        retry_form.is_valid()
        retry_form.add_error(None, exc.safe_message)
        fresh = _context(
            actor_id=actor_id,
            job_id=job_id,
            bound_item_id=item_id,
            bound_form=retry_form,
        )
        return _render_import(
            request,
            status=(409 if exc.code == "exchange.import_preview_conflict.v1" else 422),
            import_upload_form=ImportUploadForm(),
            **fresh,
        )
    return private_response(
        redirect(
            f"{reverse('authoring:import-job', kwargs={'job_id': job_id})}?updated=1"
        )
    )


def confirm_import_job(request, job_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("POST",)):
        return denied
    form = ImportConfirmForm(request.POST)
    if not form.is_valid():
        return _render_import(
            request,
            status=422,
            import_upload_form=ImportUploadForm(),
            **_context(
                actor_id=actor_id, job_id=job_id, error="导入预览已变化，请刷新后重试。"
            ),
        )
    try:
        _integrations().confirm_configured_import(
            actor_id=actor_id,
            job_id=job_id,
            expected_preview_version=form.cleaned_data["expected_preview_version"],
            trace_code=request.trace_code,
            client_ip=request.client_ip,
        )
    except ImportConfirmationError as exc:
        if exc.code == "exchange.import_not_found.v1":
            raise Http404 from None
        return _render_import(
            request,
            status=(409 if exc.code == "exchange.import_preview_conflict.v1" else 422),
            import_upload_form=ImportUploadForm(),
            **_context(actor_id=actor_id, job_id=job_id, error=exc.safe_message),
        )
    return private_response(
        redirect(
            f"{reverse('authoring:import-job', kwargs={'job_id': job_id})}?confirmed=1"
        )
    )


def import_job_status(request, job_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if denied := _method(request, ("GET",)):
        return denied
    return _render_import(
        request,
        template="authoring/partials/import_job_panel.html",
        **_context(actor_id=actor_id, job_id=job_id),
    )
