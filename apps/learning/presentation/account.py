import json
from uuid import UUID

from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from apps.accounts.public import can_upload_attachments
from apps.core.http import is_htmx_fragment_request
from apps.learning.contracts import (
    KnowledgeDocumentAccessPurpose,
    LearningCommandError,
)
from apps.learning.public import (
    create_question_bank_generation_request,
    delete_knowledge_document,
    owner_document_access_history,
    owner_knowledge_document,
    owner_knowledge_document_page,
    owner_knowledge_document_question_bank_series,
    owner_question_bank_detail,
    owner_question_bank_metadata,
    question_generation_available,
    read_knowledge_document_text,
    restore_knowledge_document,
    retry_document_review,
    retry_question_bank_generation,
    revise_question_in_bank,
    submit_knowledge_document,
    submit_learning_appeal,
    update_question_bank_series_metadata,
    withdraw_learning_appeal,
)
from apps.learning.tasks import dispatch_knowledge_review, dispatch_question_generation
from apps.media.public import RenderingError, render_markdown

from .forms import (
    KnowledgeDocumentActionForm,
    KnowledgeDocumentSubmitForm,
    LearningAppealForm,
    LearningAppealWithdrawForm,
    QuestionBankGenerationForm,
    QuestionBankMetadataForm,
    QuestionBankRetryForm,
    QuestionEditForm,
)

_SAVED_MESSAGES = {
    "submitted": "知识文档已提交审核",
    "deleted": "知识文档已进入删除冷静期",
    "restored": "知识文档已恢复",
    "retried": "知识文档已重新提交审核",
    "appealed": "申诉已提交",
    "appeal-withdrawn": "申诉已撤回",
    "generation-submitted": "题库生成任务已提交",
    "generation-retried": "题库生成任务已重新提交",
    "series-updated": "题库资料已更新",
    "question-revised": "题目修订已保存",
}


def _no_store(response: HttpResponse) -> HttpResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _login_required(request):
    target = reverse("learning:documents")
    return _no_store(
        redirect(f"{reverse('accounts:login')}?{urlencode({'next': target})}")
    )


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _dialog_context(request, *, owner_id: UUID) -> dict[str, object]:
    dialog = request.GET.get("dialog", "")
    if dialog == "history":
        document_id = _uuid(request.GET.get("document_id"))
        if document_id is None:
            return {}
        try:
            document = owner_knowledge_document(
                owner_id=owner_id,
                document_id=document_id,
            )
            history = owner_knowledge_document_question_bank_series(
                owner_id=owner_id,
                document_id=document_id,
                page=_page_number(request.GET.get("history_page")),
                page_size=20,
            )
        except LearningCommandError:
            return {}
        return {
            "dialog_kind": dialog,
            "dialog_document": document,
            "dialog_history": history,
            "dialog_history_pagination_query": urlencode(
                {"dialog": "history", "document_id": document_id}
            ),
        }
    if dialog == "series":
        series_id = _uuid(request.GET.get("series_id"))
        if series_id is None:
            return {}
        try:
            metadata = owner_question_bank_metadata(
                owner_id=owner_id,
                series_id=series_id,
            )
        except LearningCommandError:
            return {}
        return {
            "dialog_kind": dialog,
            "dialog_series": metadata,
            "dialog_return_url": _dialog_return_url(request),
            "metadata_form": QuestionBankMetadataForm(
                initial={
                    "series_id": metadata.series_id,
                    "expected_version": metadata.row_version,
                    "base_title": metadata.base_title,
                    "description": metadata.description,
                    "tags": "\n".join(metadata.tags),
                }
            ),
        }
    if dialog in {"bank", "question"}:
        bank_id = _uuid(request.GET.get("bank_id"))
        if bank_id is None:
            return {}
        try:
            bank = owner_question_bank_detail(owner_id=owner_id, bank_id=bank_id)
        except LearningCommandError:
            return {}
        context = {
            "dialog_kind": dialog,
            "dialog_bank": bank,
            "dialog_return_url": _dialog_return_url(request),
            "dialog_history_document_id": request.GET.get("history_document_id", ""),
        }
        if dialog == "question":
            logical_id = request.GET.get("question_id", "")
            question = next(
                (item for item in bank.questions if item.logical_id == logical_id),
                None,
            )
            if question is None:
                return {}
            context.update(
                {
                    "dialog_question": question,
                    "question_form": _question_edit_form(bank, question),
                }
            )
        return context
    document_id = _uuid(request.GET.get("document_id"))
    if dialog not in {"document", "appeal", "generate"} or document_id is None:
        return {}
    try:
        document = owner_knowledge_document(
            owner_id=owner_id,
            document_id=document_id,
        )
    except LearningCommandError:
        return {}
    if dialog == "appeal":
        return {
            "dialog_kind": dialog,
            "dialog_document": document,
            "appeal_form": LearningAppealForm(
                initial={
                    "document_id": document.document_id,
                    "expected_version": document.row_version,
                }
            ),
        }
    if dialog == "generate":
        if document.state != "APPROVED" or not question_generation_available():
            return {}
        return {
            "dialog_kind": dialog,
            "dialog_document": document,
            "generation_form": QuestionBankGenerationForm(
                initial={
                    "document_id": document.document_id,
                    "base_title": document.title or document.original_name or "",
                    "single_choice": True,
                    "multiple_choice": True,
                    "true_false": True,
                    "short_answer": True,
                }
            ),
        }
    try:
        source = read_knowledge_document_text(
            actor_id=owner_id,
            document_id=document.document_id,
            purpose=KnowledgeDocumentAccessPurpose.OWNER_VIEW,
            trace_code=request.trace_code,
        )
        content_html = render_markdown(source.content).html
    except (LearningCommandError, RenderingError):
        content_html = ""
    return {
        "dialog_kind": dialog,
        "dialog_document": document,
        "dialog_content_html": content_html,
        "dialog_access_history": owner_document_access_history(
            owner_id=owner_id,
            document_id=document.document_id,
            page=_page_number(request.GET.get("access_page")),
            page_size=20,
        ),
        "dialog_access_pagination_query": urlencode(
            {"dialog": "document", "document_id": document.document_id}
        ),
    }


def _dialog_return_url(request) -> str:
    history_document_id = _uuid(request.GET.get("history_document_id"))
    if history_document_id is None:
        return reverse("learning:documents")
    return f"{reverse('learning:documents')}?{urlencode({'dialog': 'history', 'document_id': history_document_id})}"


def _question_edit_form(bank, question, *, data=None):
    initial = {
        "bank_id": bank.bank_id,
        "logical_id": question.logical_id,
        "expected_bank_version": bank.row_version,
        "stem_markdown": question.stem_markdown,
        "options_text": "\n".join(
            f"{option.option_id} | {option.text}" for option in question.options
        ),
        "correct_option_ids": ", ".join(question.correct_option_ids),
        "boolean_answer": (
            "true"
            if question.boolean_answer is True
            else "false"
            if question.boolean_answer is False
            else ""
        ),
        "reference_answer": question.reference_answer,
        "scoring_points": "\n".join(question.scoring_points),
        "explanation_markdown": question.explanation_markdown,
        "revision_reason": "",
    }
    return QuestionEditForm(
        data,
        question_type=question.question_type,
        initial=initial,
    )


def _context(
    request,
    *,
    owner_id: UUID,
    upload_form=None,
    appeal_form=None,
    generation_form=None,
    metadata_form=None,
    question_form=None,
    question_bank=None,
    question_item=None,
) -> dict[str, object]:
    page = owner_knowledge_document_page(
        owner_id=owner_id,
        page=_page_number(request.GET.get("page")),
    )
    can_upload = can_upload_attachments(owner_id)
    if not can_upload and page.total_items == 0:
        raise Http404
    context = {
        "knowledge_page": page,
        "knowledge_can_upload": can_upload,
        "knowledge_upload_url": reverse(
            "media:upload", kwargs={"adapter": "knowledge-document"}
        ),
        "upload_form": upload_form or KnowledgeDocumentSubmitForm(),
        "saved_message": _SAVED_MESSAGES.get(request.GET.get("saved", ""), ""),
        "knowledge_has_active_generation": any(
            item.has_active_generation for item in page.items
        ),
        "knowledge_has_active_work": any(
            item.has_active_generation or item.state in {"REVIEW_PENDING", "REVIEWING"}
            for item in page.items
        ),
        "knowledge_generation_available": question_generation_available(),
    }
    context.update(_dialog_context(request, owner_id=owner_id))
    if appeal_form is not None:
        context["dialog_kind"] = "appeal"
        context["appeal_form"] = appeal_form
        document_id = _uuid(appeal_form.data.get("document_id"))
        if document_id is not None:
            context["dialog_document"] = owner_knowledge_document(
                owner_id=owner_id,
                document_id=document_id,
            )
    if generation_form is not None:
        context["dialog_kind"] = "generate"
        context["generation_form"] = generation_form
        document_id = _uuid(generation_form.data.get("document_id"))
        if document_id is not None:
            context["dialog_document"] = owner_knowledge_document(
                owner_id=owner_id,
                document_id=document_id,
            )
    if metadata_form is not None:
        context["dialog_kind"] = "series"
        context["metadata_form"] = metadata_form
        series_id = _uuid(metadata_form.data.get("series_id"))
        if series_id is not None:
            context["dialog_series"] = owner_question_bank_metadata(
                owner_id=owner_id,
                series_id=series_id,
            )
    if (
        question_form is not None
        and question_bank is not None
        and question_item is not None
    ):
        context["dialog_kind"] = "question"
        context["question_form"] = question_form
        context["dialog_bank"] = question_bank
        context["dialog_question"] = question_item
    return context


def _feedback(response: HttpResponse, *, key: str, message: str, level="success"):
    response.headers["HX-Trigger-After-Swap"] = json.dumps(
        {
            "kaj:feedback": {
                "key": f"knowledge-{key}",
                "level": level,
                "message": message,
                "timeout": 4500 if level == "success" else 6500,
            }
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return response


def _success_response(request, *, owner_id: UUID, saved: str):
    if not is_htmx_fragment_request(request):
        return _no_store(
            redirect(f"{reverse('learning:documents')}?{urlencode({'saved': saved})}")
        )
    response = render(
        request,
        "learning/partials/documents_workspace.html",
        _context(request, owner_id=owner_id),
    )
    response.headers["HX-Replace-Url"] = reverse("learning:documents")
    return _no_store(_feedback(response, key=saved, message=_SAVED_MESSAGES[saved]))


def _error_response(
    request,
    *,
    owner_id: UUID,
    upload_form=None,
    appeal_form=None,
    generation_form=None,
    metadata_form=None,
    question_form=None,
    question_bank=None,
    question_item=None,
    status=422,
):
    context = _context(
        request,
        owner_id=owner_id,
        upload_form=upload_form,
        appeal_form=appeal_form,
        generation_form=generation_form,
        metadata_form=metadata_form,
        question_form=question_form,
        question_bank=question_bank,
        question_item=question_item,
    )
    template = (
        "learning/partials/documents_workspace.html"
        if is_htmx_fragment_request(request)
        else "learning/documents.html"
    )
    return _no_store(render(request, template, context, status=status))


@require_http_methods(["GET", "POST"])
def documents(request):
    owner_id = getattr(request, "account_id", None)
    if owner_id is None:
        return _login_required(request)
    if request.method == "GET":
        template = (
            "learning/partials/documents_workspace.html"
            if is_htmx_fragment_request(request)
            else "learning/documents.html"
        )
        return _no_store(
            render(
                request,
                template,
                _context(request, owner_id=owner_id),
            )
        )

    action = request.POST.get("action", "")
    try:
        if action == "submit":
            form = KnowledgeDocumentSubmitForm(request.POST)
            if not form.is_valid():
                return _error_response(request, owner_id=owner_id, upload_form=form)
            submit_knowledge_document(
                owner_id=owner_id,
                asset_id=form.cleaned_data["source_asset_id"],
                statement_version=form.cleaned_data["statement_version"],
                accepted=form.cleaned_data["accepted"],
                idempotency_key=form.cleaned_data["idempotency_key"],
                dispatcher=dispatch_knowledge_review,
            )
            return _success_response(request, owner_id=owner_id, saved="submitted")

        if action == "generate":
            form = QuestionBankGenerationForm(request.POST)
            if not form.is_valid():
                return _error_response(
                    request,
                    owner_id=owner_id,
                    generation_form=form,
                )
            create_question_bank_generation_request(
                owner_id=owner_id,
                document_id=form.cleaned_data["document_id"],
                base_title=form.cleaned_data["base_title"],
                description=form.cleaned_data["description"],
                question_types=form.question_types(),
                idempotency_key=form.cleaned_data["idempotency_key"],
                dispatcher=dispatch_question_generation,
            )
            return _success_response(
                request,
                owner_id=owner_id,
                saved="generation-submitted",
            )

        if action == "retry_generation":
            form = QuestionBankRetryForm(request.POST)
            if not form.is_valid():
                return _error_response(request, owner_id=owner_id)
            retry_question_bank_generation(
                owner_id=owner_id,
                series_id=form.cleaned_data["series_id"],
                expected_version=form.cleaned_data["expected_version"],
                idempotency_key=form.cleaned_data["idempotency_key"],
                dispatcher=dispatch_question_generation,
            )
            return _success_response(
                request,
                owner_id=owner_id,
                saved="generation-retried",
            )

        if action == "update_series":
            form = QuestionBankMetadataForm(request.POST)
            if not form.is_valid():
                return _error_response(
                    request,
                    owner_id=owner_id,
                    metadata_form=form,
                )
            update_question_bank_series_metadata(
                actor_id=owner_id,
                series_id=form.cleaned_data["series_id"],
                expected_version=form.cleaned_data["expected_version"],
                base_title=form.cleaned_data["base_title"],
                description=form.cleaned_data["description"],
                tag_names=form.tag_names(),
            )
            return _success_response(
                request,
                owner_id=owner_id,
                saved="series-updated",
            )

        if action == "revise_question":
            bank_id = _uuid(request.POST.get("bank_id"))
            logical_id = request.POST.get("logical_id", "")
            if bank_id is None:
                raise LearningCommandError("learning.bank_not_found.v1", "题库不存在。")
            bank = owner_question_bank_detail(owner_id=owner_id, bank_id=bank_id)
            question = next(
                (item for item in bank.questions if item.logical_id == logical_id),
                None,
            )
            if question is None:
                raise LearningCommandError(
                    "learning.question_not_found.v1", "题目不存在。"
                )
            form = QuestionEditForm(
                request.POST,
                question_type=question.question_type,
            )
            if not form.is_valid():
                return _error_response(
                    request,
                    owner_id=owner_id,
                    question_form=form,
                    question_bank=bank,
                    question_item=question,
                )
            revise_question_in_bank(
                actor_id=owner_id,
                bank_id=bank.bank_id,
                expected_bank_version=form.cleaned_data["expected_bank_version"],
                question=form.content_draft(),
                revision_reason=form.cleaned_data["revision_reason"],
            )
            return _success_response(
                request,
                owner_id=owner_id,
                saved="question-revised",
            )

        if action in {"delete", "restore", "retry"}:
            form = KnowledgeDocumentActionForm(request.POST)
            if not form.is_valid():
                return _error_response(request, owner_id=owner_id)
            values = {
                "owner_id": owner_id,
                "document_id": form.cleaned_data["document_id"],
                "expected_version": form.cleaned_data["expected_version"],
            }
            if action == "delete":
                delete_knowledge_document(**values)
                saved = "deleted"
            elif action == "restore":
                restore_knowledge_document(**values)
                saved = "restored"
            else:
                retry_document_review(
                    owner_id=values["owner_id"],
                    document_id=values["document_id"],
                    expected_document_version=values["expected_version"],
                    dispatcher=dispatch_knowledge_review,
                )
                saved = "retried"
            return _success_response(request, owner_id=owner_id, saved=saved)

        if action == "appeal":
            form = LearningAppealForm(request.POST)
            if not form.is_valid():
                return _error_response(request, owner_id=owner_id, appeal_form=form)
            submit_learning_appeal(
                owner_id=owner_id,
                document_id=form.cleaned_data["document_id"],
                expected_document_version=form.cleaned_data["expected_version"],
                reason_markdown=form.cleaned_data["reason_markdown"],
            )
            return _success_response(request, owner_id=owner_id, saved="appealed")

        if action == "withdraw_appeal":
            form = LearningAppealWithdrawForm(request.POST)
            if not form.is_valid():
                return _error_response(request, owner_id=owner_id)
            withdraw_learning_appeal(
                owner_id=owner_id,
                appeal_id=form.cleaned_data["appeal_id"],
                expected_version=form.cleaned_data["expected_version"],
            )
            return _success_response(
                request,
                owner_id=owner_id,
                saved="appeal-withdrawn",
            )
        raise LearningCommandError("learning.action_invalid.v1", "知识文档操作不合法。")
    except LearningCommandError as error:
        if action == "submit":
            form = KnowledgeDocumentSubmitForm(request.POST)
            form.is_valid()
            form.add_error(None, error.safe_message)
            return _error_response(request, owner_id=owner_id, upload_form=form)
        if action == "appeal":
            form = LearningAppealForm(request.POST)
            form.is_valid()
            form.add_error(None, error.safe_message)
            return _error_response(request, owner_id=owner_id, appeal_form=form)
        if action == "generate":
            form = QuestionBankGenerationForm(request.POST)
            form.is_valid()
            form.add_error(None, error.safe_message)
            return _error_response(
                request,
                owner_id=owner_id,
                generation_form=form,
            )
        if action == "update_series":
            form = QuestionBankMetadataForm(request.POST)
            form.is_valid()
            form.add_error(None, error.safe_message)
            return _error_response(
                request,
                owner_id=owner_id,
                metadata_form=form,
            )
        if action == "revise_question":
            bank_id = _uuid(request.POST.get("bank_id"))
            logical_id = request.POST.get("logical_id", "")
            if bank_id is not None:
                bank = owner_question_bank_detail(owner_id=owner_id, bank_id=bank_id)
                question = next(
                    (item for item in bank.questions if item.logical_id == logical_id),
                    None,
                )
                if question is not None:
                    form = QuestionEditForm(
                        request.POST,
                        question_type=question.question_type,
                    )
                    form.is_valid()
                    form.add_error(None, error.safe_message)
                    return _error_response(
                        request,
                        owner_id=owner_id,
                        question_form=form,
                        question_bank=bank,
                        question_item=question,
                    )
        response = _error_response(request, owner_id=owner_id)
        return _feedback(
            response,
            key="error",
            message=error.safe_message,
            level="error",
        )


__all__ = ["documents"]
