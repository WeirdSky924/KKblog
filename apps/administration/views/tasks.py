from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.public import is_administrator
from apps.administration.forms.operations import TaskRunFilterForm
from apps.agents.public import task_run_metadata
from apps.operations.public import current_monitoring_status, task_run_records


@require_GET
def task_runs(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    form = TaskRunFilterForm(request.GET)
    status = 200
    if form.is_valid():
        selected_status = form.cleaned_data["status"]
        rows = task_run_records(
            status=selected_status,
            is_admin=True,
            metadata_provider=task_run_metadata,
        )
    else:
        selected_status = ""
        rows = ()
        status = 422
    monitoring = current_monitoring_status(is_admin=True)
    return render(
        request,
        "administration/tasks.html",
        {
            "task_filter_form": form,
            "task_rows": rows,
            "selected_task_status": selected_status,
            "monitoring": monitoring,
        },
        status=status,
    )


__all__ = ["task_runs"]
