import json
from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from apps.accounts.public import is_active_account
from apps.learning.contracts import LearningCommandError, QuizMasteryStatus
from apps.learning.public import (
    delete_all_quiz_records,
    delete_quiz_records,
    iter_quiz_record_csv,
    pending_quiz_records,
    quiz_record_bank_options,
    quiz_record_delete_preflight,
    quiz_record_detail,
    quiz_record_page,
    request_quiz_record_deletion,
    restore_quiz_record,
    set_wrong_question_mastery,
    wrong_question_bank_options,
    wrong_question_page,
)

from .record_forms import (
    QuizRecordActionForm,
    QuizRecordBatchForm,
    QuizRecordClearForm,
    QuizRecordFilterForm,
    WrongQuestionFilterForm,
    WrongQuestionMasteryForm,
)


def _no_store(response: HttpResponse) -> HttpResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _login_required(request: HttpRequest, target_name: str) -> HttpResponse:
    target = request.get_full_path()
    return _no_store(
        redirect(f"{reverse('accounts:login')}?{urlencode({'next': target})}")
    )


def _uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _wrong_query(form: WrongQuestionFilterForm) -> dict[str, object]:
    return {
        "mastery_status": form.cleaned_data.get("mastery_status")
        or QuizMasteryStatus.TO_REVIEW,
        "bank_id": form.cleaned_data.get("bank_id") or None,
        "page": _page_number(form.data.get("page")),
        "page_size": form.cleaned_data.get("page_size") or 20,
    }


def _record_query(form: QuizRecordFilterForm) -> dict[str, object]:
    return {
        "bank_id": form.cleaned_data.get("bank_id") or None,
        "source": form.cleaned_data.get("source") or "",
        "status": form.cleaned_data.get("status") or "",
        "started_from": form.cleaned_data.get("started_from"),
        "started_to": form.cleaned_data.get("started_to"),
        "page": _page_number(form.data.get("page")),
        "page_size": form.cleaned_data.get("page_size") or 20,
    }


def _wrong_context(request, *, form=None, page_error="", saved=""):
    bank_options = wrong_question_bank_options(account_id=request.account_id)
    form = form or WrongQuestionFilterForm(
        request.GET or None,
        bank_options=bank_options,
    )
    if not form.is_bound:
        form.is_valid()
    query = _wrong_query(form) if form.is_valid() else {}
    try:
        page = wrong_question_page(account_id=request.account_id, **query)
    except LearningCommandError as error:
        page = wrong_question_page(account_id=request.account_id)
        page_error = page_error or error.safe_message
    return {
        "wrong_page": page,
        "wrong_filter_form": form,
        "page_error": page_error,
        "saved": saved,
        "wrong_mastery_choices": QuizMasteryStatus.choices,
    }


def _record_context(request, *, form=None, page_error="", saved=""):
    bank_options = quiz_record_bank_options(account_id=request.account_id)
    form = form or QuizRecordFilterForm(request.GET or None, bank_options=bank_options)
    if not form.is_bound:
        form.is_valid()
    query = _record_query(form) if form.is_valid() else {}
    try:
        page = quiz_record_page(account_id=request.account_id, **query)
    except LearningCommandError as error:
        page = quiz_record_page(account_id=request.account_id)
        page_error = page_error or error.safe_message
    return {
        "record_page": page,
        "pending_records": pending_quiz_records(account_id=request.account_id),
        "record_versions_json": json.dumps(
            {str(item.attempt_id): item.row_version for item in page.items},
            ensure_ascii=False,
        ),
        "record_filter_form": form,
        "page_error": page_error,
        "saved": saved,
    }


@require_http_methods(["GET", "POST"])
def wrong_book(request: HttpRequest) -> HttpResponse:
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request, "learning:wrong-book")
    if request.method == "POST":
        form = WrongQuestionMasteryForm(request.POST)
        if form.is_valid():
            try:
                set_wrong_question_mastery(
                    account_id=request.account_id,
                    wrong_question_id=form.cleaned_data["wrong_question_id"],
                    expected_version=form.cleaned_data["expected_version"],
                    mastery_status=form.cleaned_data["mastery_status"],
                )
            except LearningCommandError as error:
                return _no_store(
                    render(
                        request,
                        "learning/wrong_book.html",
                        _wrong_context(request, page_error=error.safe_message),
                        status=409 if "conflict" in error.code else 422,
                    )
                )
            return redirect(f"{reverse('learning:wrong-book')}?saved=mastery")
        return _no_store(
            render(
                request,
                "learning/wrong_book.html",
                _wrong_context(request, page_error="请求不合法。"),
                status=422,
            )
        )
    return _no_store(
        render(
            request,
            "learning/wrong_book.html",
            _wrong_context(request, saved=request.GET.get("saved", "")),
        )
    )


def _record_redirect(request: HttpRequest, *, saved: str) -> HttpResponse:
    params = request.GET.copy()
    params.pop("saved", None)
    params["saved"] = saved
    return redirect(f"{reverse('learning:records')}?{params.urlencode()}")


@require_http_methods(["GET", "POST"])
def records(request: HttpRequest) -> HttpResponse:
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request, "learning:records")
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            single_attempt_id = request.POST.get("single_attempt_id")
            if single_attempt_id:
                version = int(
                    request.POST.get("single_expected_version")
                    or request.POST.get("expected_version")
                    or 0
                )
                request_quiz_record_deletion(
                    account_id=request.account_id,
                    attempt_id=single_attempt_id,
                    expected_version=version,
                )
                return _record_redirect(request, saved="deleted")
            if action in {"delete", "restore"}:
                form = QuizRecordActionForm(request.POST)
                if not form.is_valid():
                    raise LearningCommandError(
                        "learning.quiz_record_invalid.v1", "请求不合法。"
                    )
                (
                    request_quiz_record_deletion(
                        account_id=request.account_id,
                        attempt_id=form.cleaned_data["attempt_id"],
                        expected_version=form.cleaned_data["expected_version"],
                    )
                    if action == "delete"
                    else restore_quiz_record(
                        account_id=request.account_id,
                        attempt_id=form.cleaned_data["attempt_id"],
                        expected_version=form.cleaned_data["expected_version"],
                    )
                )
                return _record_redirect(
                    request, saved="deleted" if action == "delete" else "restored"
                )
            if action == "batch-delete":
                form = QuizRecordBatchForm(request.POST)
                if not form.is_valid():
                    raise LearningCommandError(
                        "learning.quiz_batch_invalid.v1", "批量请求不合法。"
                    )
                selected_ids = request.POST.getlist("attempt_id")
                expected_count = form.cleaned_data["expected_count"]
                if (
                    quiz_record_delete_preflight(
                        account_id=request.account_id, attempt_ids=selected_ids
                    )
                    != expected_count
                ):
                    raise LearningCommandError(
                        "learning.quiz_record_count_conflict.v1",
                        "记录数量已变化，请重新确认。",
                    )
                delete_quiz_records(
                    account_id=request.account_id,
                    attempt_ids=selected_ids,
                    expected_versions=form.versions(),
                )
                return _record_redirect(request, saved="deleted")
            if action == "clear":
                form = QuizRecordClearForm(request.POST)
                if not form.is_valid():
                    raise LearningCommandError(
                        "learning.quiz_batch_invalid.v1", "清空请求不合法。"
                    )
                delete_all_quiz_records(
                    account_id=request.account_id,
                    expected_count=form.cleaned_data["expected_count"],
                )
                return _record_redirect(request, saved="deleted")
            raise LearningCommandError(
                "learning.quiz_action_invalid.v1", "操作不支持。"
            )
        except LearningCommandError as error:
            return _no_store(
                render(
                    request,
                    "learning/records.html",
                    _record_context(request, page_error=error.safe_message),
                    status=409 if "conflict" in error.code else 422,
                )
            )
    return _no_store(
        render(
            request,
            "learning/records.html",
            _record_context(request, saved=request.GET.get("saved", "")),
        )
    )


@require_http_methods(["GET"])
def record_detail(request: HttpRequest, attempt_id) -> HttpResponse:
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request, "learning:record-detail")
    try:
        detail = quiz_record_detail(
            account_id=request.account_id, attempt_id=attempt_id
        )
    except LearningCommandError as error:
        raise Http404 from error
    return _no_store(
        render(request, "learning/record_detail.html", {"attempt": detail})
    )


@require_http_methods(["GET"])
def records_export(request: HttpRequest) -> HttpResponse:
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request, "learning:records")
    bank_options = quiz_record_bank_options(account_id=request.account_id)
    form = QuizRecordFilterForm(request.GET or None, bank_options=bank_options)
    if form.is_bound and not form.is_valid():
        return _no_store(HttpResponse("筛选参数不合法。", status=422))
    query = (
        _record_query(form)
        if form.is_bound
        else {
            "bank_id": None,
            "source": "",
            "status": "",
            "started_from": None,
            "started_to": None,
        }
    )
    stream = iter_quiz_record_csv(
        account_id=request.account_id,
        **{
            key: query[key]
            for key in ("bank_id", "source", "status", "started_from", "started_to")
        },
    )
    response = StreamingHttpResponse(stream, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="quiz-records.csv"'
    return _no_store(response)


__all__ = ["record_detail", "records", "records_export", "wrong_book"]
