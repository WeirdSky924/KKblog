import logging
from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.core.http import is_htmx_fragment_request
from apps.core.observability.trace import new_trace_code
from apps.learning.public import (
    KnowledgeDocumentAccessPurpose,
    LearningAdminTargetType,
    LearningCommandError,
    admin_learning_appeal_detail,
    admin_learning_appeal_page,
    admin_learning_document_detail,
    admin_learning_document_page,
    administer_knowledge_document,
    execute_learning_admin_batch,
    preflight_learning_admin_batch,
    read_knowledge_document_text,
    review_learning_appeal,
)
from apps.learning.tasks import dispatch_knowledge_review
from apps.media.public import render_markdown
from apps.media.storage import FilesystemMediaStorage

from ..forms.learning import (
    LearningAppealDecisionForm,
    LearningBatchForm,
    LearningDocumentFilterForm,
)
from ..presentation.feedback import learning_batch_feedback

logger = logging.getLogger("kaj.administration.learning")


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "trace_code": getattr(request, "trace_code", ""),
        "client_ip": request.client_ip,
    }


def _filter_query(request: HttpRequest) -> str:
    params = request.GET.copy()
    for key in (
        "page",
        "dialog",
        "document_id",
        "appeal_id",
        "access_page",
        "appeal_page",
        "batch_action",
        "selected",
        "batch_type",
        "saved",
        "total",
        "succeeded",
        "failed",
    ):
        params.pop(key, None)
    return params.urlencode()


def _batch_form(
    request: HttpRequest, *, target_values=(), data=None, require_reason=False
):
    values = tuple(target_values)
    return LearningBatchForm(
        data,
        target_values=values,
        require_reason=require_reason,
        initial={
            "target_type": LearningAdminTargetType.DOCUMENT,
            "targets": values,
            "confirm": False,
        },
    )


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    page_error: str = "",
    batch_preview=None,
    batch_form=None,
    appeal=None,
    appeal_form=None,
    document_detail=None,
    document_html: str = "",
    saved: str = "",
) -> HttpResponse:
    effective_saved = saved or request.GET.get("saved", "")
    filter_form = LearningDocumentFilterForm(request.GET or None)
    if filter_form.is_valid():
        cleaned = filter_form.cleaned_data
        page = admin_learning_document_page(
            actor_id=request.account_id,
            keyword=cleaned.get("q", ""),
            state=cleaned.get("state", ""),
            page=cleaned.get("page") or 1,
            page_size=20,
        )
    else:
        page = admin_learning_document_page(actor_id=request.account_id)
        if request.GET:
            status = 422
    fragment = (
        is_htmx_fragment_request(request)
        and batch_preview is None
        and document_detail is None
        and appeal is None
    )
    appeals = (
        None
        if fragment
        else admin_learning_appeal_page(
            actor_id=request.account_id,
            state="PENDING",
            page=_page_number(request.GET.get("appeal_page")),
            page_size=20,
        )
    )
    template_name = (
        "administration/partials/learning_document_queue.html"
        if fragment
        else "administration/learning_documents.html"
    )
    response = render(
        request,
        template_name,
        {
            "document_page": page,
            "filter_form": filter_form,
            "appeal_page": appeals,
            "batch_preview": batch_preview,
            "batch_form": batch_form,
            "appeal": appeal,
            "appeal_form": appeal_form,
            "document_detail": document_detail,
            "document_html": document_html,
            "document_access_pagination_query": (
                urlencode(
                    {
                        "dialog": "document",
                        "document_id": document_detail.item.document_id,
                    }
                )
                if document_detail is not None
                else ""
            ),
            "page_error": page_error,
            "saved": effective_saved,
            "batch_feedback": learning_batch_feedback(
                request.GET,
                saved=effective_saved,
            ),
            "filter_query": _filter_query(request),
            "appeal_pagination_query": _filter_query(request),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _read_document(request: HttpRequest, document_id):
    try:
        identity = UUID(str(document_id))
    except (TypeError, ValueError):
        raise LearningCommandError(
            "learning.document_not_found.v1", "知识文档不存在。"
        ) from None
    detail = admin_learning_document_detail(
        actor_id=request.account_id,
        document_id=identity,
        page=_page_number(request.GET.get("access_page")),
        page_size=20,
    )
    text = read_knowledge_document_text(
        actor_id=request.account_id,
        document_id=identity,
        purpose=KnowledgeDocumentAccessPurpose.ADMIN_REVIEW,
        trace_code=getattr(request, "trace_code", None) or new_trace_code(),
        storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
    )
    return detail, render_markdown(text.content).html


def learning_documents(request: HttpRequest) -> HttpResponse:
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
                    "target_type": LearningAdminTargetType.DOCUMENT,
                    "action": action,
                    "targets": selected,
                    "reason_code": "",
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
                # The preview must require an explicit click; never render the
                # bound request value as an already-checked confirmation.
                form.data = form.data.copy()
                form.data["confirm"] = ""
                return _render(request, batch_preview=preview, batch_form=form)
            return _render(request, status=422, batch_form=form)
        document_detail = None
        document_html = ""
        if request.GET.get("dialog") == "document":
            try:
                document_detail, document_html = _read_document(
                    request, request.GET.get("document_id")
                )
            except LearningCommandError as error:
                logger.warning(
                    "Learning document dialog unavailable code=%s", error.code
                )
                raise Http404 from None
        appeal = None
        appeal_form = None
        if request.GET.get("dialog") == "appeal":
            try:
                appeal = admin_learning_appeal_detail(
                    actor_id=request.account_id,
                    appeal_id=request.GET.get("appeal_id"),
                )
            except LearningCommandError:
                raise Http404 from None
            appeal_form = LearningAppealDecisionForm(
                initial={
                    "appeal_id": appeal.appeal_id,
                    "expected_version": appeal.row_version,
                    "decision": "REJECTED",
                    "confirm": "learning_appeal",
                }
            )
        return _render(
            request,
            document_detail=document_detail,
            document_html=document_html,
            appeal=appeal,
            appeal_form=appeal_form,
        )
    return _post(request)


def _post(request: HttpRequest) -> HttpResponse:
    action_values = request.POST.getlist("action")
    command = request.POST.get("command") or (
        "learning_batch_execute"
        if "learning_batch_execute" in action_values
        else request.POST.get("action", "")
    )
    if command == "learning_batch_execute":
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
                page_error="没有收到已勾选的文档，请返回队列后重新选择。",
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
                page_error="本次没有执行任何文档，请重新选择后再试。",
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
        return redirect(f"{reverse('admin:learning-documents')}?{urlencode(params)}")
    if command == "learning_appeal_review":
        form = LearningAppealDecisionForm(request.POST)
        if not form.is_valid():
            return _render(request, status=422, appeal_form=form)
        try:
            review_learning_appeal(
                administrator_id=request.account_id,
                appeal_id=form.cleaned_data["appeal_id"],
                expected_version=form.cleaned_data["expected_version"],
                decision=form.cleaned_data["decision"],
                decision_markdown=form.cleaned_data["decision_markdown"],
                dispatcher=dispatch_knowledge_review,
                **_meta(request),
            )
        except LearningCommandError as error:
            form.add_error(None, error.safe_message)
            try:
                appeal = admin_learning_appeal_detail(
                    actor_id=request.account_id,
                    appeal_id=form.cleaned_data.get("appeal_id"),
                )
            except LearningCommandError:
                appeal = None
            return _render(
                request,
                status=409 if "conflict" in error.code else 422,
                appeal=appeal,
                appeal_form=form,
            )
        return redirect(f"{reverse('admin:learning-documents')}?saved=appeal")
    if command == "learning_document_action":
        try:
            administer_knowledge_document(
                administrator_id=request.account_id,
                document_id=request.POST.get("document_id"),
                expected_version=int(request.POST.get("expected_version", "")),
                action=request.POST.get("document_action", ""),
                reason_code=request.POST.get("reason_code", ""),
                **_meta(request),
            )
        except (LearningCommandError, TypeError, ValueError) as error:
            message = (
                error.safe_message
                if isinstance(error, LearningCommandError)
                else "文档管理操作不合法。"
            )
            return _render(request, status=422, page_error=message)
        return redirect(f"{reverse('admin:learning-documents')}?saved=document")
    raise Http404


__all__ = ["learning_documents"]
