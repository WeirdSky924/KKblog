from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from apps.accounts.public import is_active_account
from apps.core.ids import new_ulid
from apps.learning.contracts import (
    QUIZ_QUESTION_TYPE_ORDER,
    QuestionType,
    QuizAttemptMode,
    QuizAttemptSource,
)
from apps.learning.public import (
    LearningCommandError,
    PublicQuestionBankFilterError,
    PublicQuestionBankFilters,
    PublicQuestionBankSort,
    assess_quiz_short_answer,
    public_question_bank_filter_options,
    public_question_bank_page,
    quiz_attempt_detail,
    quiz_configuration,
    save_quiz_response,
    start_quiz_attempt,
    start_wrong_question_attempt,
    submit_quiz_attempt,
    submit_quiz_response,
    wrong_question_quiz_configuration,
)

from .public_forms import PublicQuestionBankFilterForm
from .quiz_forms import (
    QuizAssessmentForm,
    QuizResponseForm,
    QuizStartForm,
    QuizSubmitForm,
)


def _no_store(response: HttpResponse) -> HttpResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _login_required(request: HttpRequest) -> HttpResponse:
    target = request.get_full_path()
    return _no_store(
        redirect(f"{reverse('accounts:login')}?{urlencode({'next': target})}")
    )


def _uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


_QUESTION_TYPE_LABELS = {
    QuestionType.SINGLE_CHOICE: "单选题",
    QuestionType.MULTIPLE_CHOICE: "多选题",
    QuestionType.TRUE_FALSE: "判断题",
    QuestionType.SHORT_ANSWER: "简答题",
}


def _has_answer(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def _navigation_state(response, *, submitted: bool = False) -> str:
    answered = _has_answer(response.answer)
    if not getattr(response, "answer_revealed", submitted):
        return "answered" if answered else ""
    if response.question_type == QuestionType.SHORT_ANSWER:
        self_assessment = getattr(response, "self_assessment", None)
        if self_assessment == "MASTERED":
            return "correct"
        if self_assessment == "NOT_MASTERED":
            return "wrong"
        return "pending"
    return "correct" if response.is_correct else "wrong"


def _question_type_choices(options):
    return tuple((item.value, f"{item.label}（{item.count} 题）") for item in options)


def _display_options(options):
    return tuple(
        {
            **option,
            "label": chr(ord("A") + index),
        }
        for index, option in enumerate(options)
    )


def _configuration_form(
    configuration, *, data=None, source=QuizAttemptSource.QUESTION_BANK, wrong=None
):
    initial = {
        "bank_id": configuration.bank_id,
        "expected_revision_id": configuration.revision_id,
        "source": source,
        "mode": QuizAttemptMode.EXAM,
        "question_types": tuple(item.value for item in configuration.question_types),
        "question_count": configuration.question_count,
        "timed": False,
        "duration_minutes": 30,
        "random_questions": True,
        "random_options": True,
        "expected_source_keys": tuple(wrong.source_keys if wrong else ()),
    }
    return QuizStartForm(
        data,
        question_type_choices=_question_type_choices(configuration.question_types),
        initial=initial,
    )


def _quiz_filter_query(request):
    query = request.GET.copy()
    query.pop("bank_id", None)
    query.pop("source", None)
    return query


def _quiz_filter_count(form):
    if not form.is_bound or not form.is_valid():
        return 0
    cleaned = form.cleaned_data
    return sum(
        (
            len(cleaned.get("tags") or ()),
            len(cleaned.get("question_types") or ()),
            bool(cleaned.get("q")),
            bool(cleaned.get("author")),
            bool(cleaned.get("min_questions")),
            bool(cleaned.get("max_questions")),
            bool(cleaned.get("published_from")),
            bool(cleaned.get("published_to")),
            cleaned.get("sort") not in (None, "", PublicQuestionBankSort.LATEST),
        )
    )


def _quiz_page_query(request, page_number: int) -> str:
    values = request.GET.copy()
    values["page"] = str(page_number)
    if not values.get("sort"):
        values["sort"] = PublicQuestionBankSort.LATEST
    return values.urlencode()


def _quiz_filter_state(request, *, page_error=""):
    options = public_question_bank_filter_options()
    query = _quiz_filter_query(request)
    filter_form = PublicQuestionBankFilterForm(
        query or None,
        options=options,
        initial={"sort": PublicQuestionBankSort.LATEST},
    )
    filters = PublicQuestionBankFilters()
    filter_error = page_error
    status = 200
    if query:
        if filter_form.is_valid():
            try:
                filters = filter_form.filters(page=max(1, int(query.get("page") or 1)))
            except (PublicQuestionBankFilterError, ValueError):
                filter_error = filter_error or "筛选条件需要修改。"
                status = 422
        else:
            filter_error = filter_error or "筛选条件需要修改。"
            status = 422
    try:
        page = public_question_bank_page(filters=filters)
    except PublicQuestionBankFilterError:
        page = public_question_bank_page(filters=PublicQuestionBankFilters())
        filter_error = filter_error or "筛选条件需要修改。"
        status = 422
    preserved = {}
    if request.GET.get("bank_id"):
        preserved["bank_id"] = request.GET["bank_id"]
    if request.GET.get("source"):
        preserved["source"] = request.GET["source"]
    bank_query = request.GET.copy()
    bank_query.pop("bank_id", None)
    pagination_query = request.GET.copy()
    pagination_query.pop("page", None)
    clear_url = reverse("learning:quiz-index")
    if preserved:
        clear_url = f"{clear_url}?{urlencode(preserved)}"
    active_count = _quiz_filter_count(filter_form)
    return {
        "bank_page": page,
        "quiz_filter_form": filter_form,
        "quiz_filter_options": options,
        "quiz_active_filters": active_count,
        "quiz_filters_open": bool(active_count or filter_form.errors),
        "quiz_filter_error": filter_error,
        "quiz_clear_url": clear_url,
        "quiz_bank_query": bank_query.urlencode(),
        "quiz_pagination_query": pagination_query.urlencode(),
        "quiz_source": request.GET.get("source", QuizAttemptSource.QUESTION_BANK),
        "quiz_previous_query": (
            _quiz_page_query(request, page.page_number - 1) if page.has_previous else ""
        ),
        "quiz_next_query": (
            _quiz_page_query(request, page.page_number + 1) if page.has_next else ""
        ),
        "quiz_filter_status": status,
    }


def _index_context(
    request,
    *,
    form=None,
    selected=None,
    page=None,
    page_error="",
    filter_state=None,
):
    state = filter_state or _quiz_filter_state(request, page_error=page_error)
    if page is not None:
        state["bank_page"] = page
    return {
        **state,
        "selected_configuration": selected,
        "start_form": form,
        "page_error": page_error,
    }


def _render_quiz_index(request, context, *, status=200):
    template = (
        "learning/partials/quiz_workspace.html"
        if request.headers.get("HX-Request") == "true"
        else "learning/quiz_index.html"
    )
    return _no_store(render(request, template, context, status=status))


def _attempt_context(
    request, *, detail, response_forms=None, submit_form=None, page_error="", saved=""
):
    forms = response_forms or tuple(
        QuizResponseForm(
            initial={
                "attempt_id": detail.attempt_id,
                "response_id": response.response_id,
                "expected_version": response.row_version,
                "request_id": new_ulid(),
                "question_type": response.question_type,
                "answer": response.answer if isinstance(response.answer, str) else "",
            }
        )
        for response in detail.responses
    )
    entries = []
    for response, response_form in zip(detail.responses, forms, strict=True):
        assessment_form = None
        if (
            response.answer_revealed
            and response.question_type == QuestionType.SHORT_ANSWER
            and response.self_assessment is None
        ):
            assessment_form = QuizAssessmentForm(
                initial={
                    "attempt_id": detail.attempt_id,
                    "response_id": response.response_id,
                    "expected_version": response.row_version,
                    "request_id": new_ulid(),
                }
            )
        entries.append(
            {
                "response": response,
                "form": response_form,
                "assessment_form": assessment_form,
                "question_type_label": _QUESTION_TYPE_LABELS.get(
                    response.question_type, response.question_type
                ),
                "display_options": _display_options(response.options),
                "nav_state": _navigation_state(response),
            }
        )
    question_groups = tuple(
        {
            "question_type": question_type,
            "label": _QUESTION_TYPE_LABELS[question_type],
            "entries": tuple(
                entry
                for entry in entries
                if entry["response"].question_type == question_type
            ),
        }
        for question_type in QUIZ_QUESTION_TYPE_ORDER
        if any(entry["response"].question_type == question_type for entry in entries)
    )
    has_revealed_response = any(
        response.answer_revealed for response in detail.responses
    )
    return {
        "attempt": detail,
        "response_entries": tuple(entries),
        "has_revealed_response": has_revealed_response,
        "practice_submit_response": next(
            (response for response in detail.responses if not response.answer_revealed),
            None,
        ),
        "question_groups": question_groups,
        "submit_form": submit_form
        or QuizSubmitForm(
            initial={"attempt_id": detail.attempt_id, "request_id": new_ulid()}
        ),
        "page_error": page_error,
        "saved": saved,
    }


@require_http_methods(["GET", "POST"])
def quiz_index(request: HttpRequest) -> HttpResponse:
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request)
    if request.method == "GET":
        filter_state = _quiz_filter_state(request)
        page = filter_state["bank_page"]
        bank_id = _uuid(request.GET.get("bank_id"))
        if bank_id is None:
            return _render_quiz_index(
                request,
                _index_context(request, page=page, filter_state=filter_state),
                status=filter_state["quiz_filter_status"],
            )
        try:
            source = request.GET.get("source", QuizAttemptSource.QUESTION_BANK)
            if source == QuizAttemptSource.WRONG_QUESTIONS:
                configuration = wrong_question_quiz_configuration(
                    account_id=request.account_id,
                    bank_id=bank_id,
                )
                form = _configuration_form(
                    configuration,
                    source=source,
                    wrong=configuration,
                )
            else:
                configuration = quiz_configuration(
                    account_id=request.account_id,
                    bank_id=bank_id,
                )
                form = _configuration_form(configuration)
        except LearningCommandError as error:
            return _render_quiz_index(
                request,
                _index_context(
                    request,
                    page=page,
                    page_error=error.safe_message,
                    filter_state=filter_state,
                ),
                status=404,
            )
        return _render_quiz_index(
            request,
            _index_context(
                request,
                page=page,
                selected=configuration,
                form=form,
                filter_state=filter_state,
            ),
            status=filter_state["quiz_filter_status"],
        )
    page = public_question_bank_page(filters=PublicQuestionBankFilters())
    try:
        source = request.POST.get("source", QuizAttemptSource.QUESTION_BANK)
        if source == QuizAttemptSource.WRONG_QUESTIONS:
            posted_configuration = wrong_question_quiz_configuration(
                account_id=request.account_id,
                bank_id=request.POST.get("bank_id"),
            )
        else:
            posted_configuration = quiz_configuration(
                account_id=request.account_id,
                bank_id=request.POST.get("bank_id"),
            )
    except LearningCommandError as error:
        return _no_store(
            render(
                request,
                "learning/quiz_index.html",
                _index_context(request, page=page, page_error=error.safe_message),
                status=404,
            )
        )
    form = _configuration_form(
        posted_configuration,
        data=request.POST,
        source=source,
        wrong=posted_configuration
        if source == QuizAttemptSource.WRONG_QUESTIONS
        else None,
    )
    if not form.is_valid():
        return _no_store(
            render(
                request,
                "learning/quiz_index.html",
                _index_context(request, page=page, selected=True, form=form),
                status=422,
            )
        )
    try:
        common = {
            "account_id": request.account_id,
            "bank_id": form.cleaned_data["bank_id"],
            "expected_revision_id": form.cleaned_data["expected_revision_id"],
            "question_types": form.cleaned_data["question_types"],
            "question_count": form.cleaned_data["question_count"],
            "timed": form.cleaned_data["timed"],
            "duration_minutes": form.cleaned_data["duration_minutes"],
            "random_questions": form.cleaned_data["random_questions"],
            "random_options": form.cleaned_data["random_options"],
            "mode": form.cleaned_data["mode"],
        }
        started = (
            start_wrong_question_attempt(
                **common,
                expected_source_keys=form.source_keys(),
            )
            if form.cleaned_data["source"] == QuizAttemptSource.WRONG_QUESTIONS
            else start_quiz_attempt(**common)
        )
    except LearningCommandError as error:
        form.add_error(None, error.safe_message)
        return _no_store(
            render(
                request,
                "learning/quiz_index.html",
                _index_context(request, page=page, selected=True, form=form),
                status=409 if "conflict" in error.code else 422,
            )
        )
    return redirect(
        reverse("learning:quiz-attempt", kwargs={"attempt_id": started.attempt_id})
    )


@require_http_methods(["GET"])
def quiz_attempt(request: HttpRequest, attempt_id):
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request)
    try:
        detail = quiz_attempt_detail(
            account_id=request.account_id, attempt_id=attempt_id
        )
    except LearningCommandError as error:
        raise Http404 from error
    return _no_store(
        render(
            request,
            "learning/quiz_attempt.html",
            _attempt_context(
                request,
                detail=detail,
                saved=request.GET.get("saved", ""),
            ),
        )
    )


@require_http_methods(["POST"])
def quiz_save_response(request: HttpRequest, response_id):
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request)
    form = QuizResponseForm(request.POST)
    if not form.is_valid():
        return _no_store(HttpResponse("答案请求不合法。", status=422))
    answer = _answer_from_request(request, form)
    try:
        saved = save_quiz_response(
            account_id=request.account_id,
            attempt_id=form.cleaned_data["attempt_id"],
            response_id=response_id,
            expected_version=form.cleaned_data["expected_version"],
            request_id=form.cleaned_data["request_id"],
            answer=answer,
        )
    except LearningCommandError as error:
        return _no_store(
            HttpResponse(
                error.safe_message, status=409 if "conflict" in error.code else 422
            )
        )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        response = HttpResponse(status=204)
        response.headers["X-Quiz-Response-Version"] = str(saved.row_version)
        response.headers["X-Quiz-Saved-At"] = saved.saved_at.isoformat()
        return _no_store(response)
    return redirect(
        reverse(
            "learning:quiz-attempt",
            kwargs={"attempt_id": form.cleaned_data["attempt_id"]},
        )
        + "?saved=response"
    )


def _answer_from_request(request: HttpRequest, form: QuizResponseForm):
    question_type = form.cleaned_data["question_type"]
    if question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
        return request.POST.getlist("answer")
    if question_type == QuestionType.TRUE_FALSE:
        raw_boolean = request.POST.get("answer")
        return None if raw_boolean is None else raw_boolean == "true"
    return request.POST.get("answer", "")


@require_http_methods(["POST"])
def quiz_submit_response(request: HttpRequest, response_id):
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request)
    form = QuizResponseForm(request.POST)
    if not form.is_valid():
        return _no_store(HttpResponse("答案请求不合法。", status=422))
    try:
        submit_quiz_response(
            account_id=request.account_id,
            attempt_id=form.cleaned_data["attempt_id"],
            response_id=response_id,
            expected_version=form.cleaned_data["expected_version"],
            request_id=form.cleaned_data["request_id"],
            answer=_answer_from_request(request, form),
        )
    except LearningCommandError as error:
        return _no_store(
            HttpResponse(
                error.safe_message, status=409 if "conflict" in error.code else 422
            )
        )
    return redirect(
        reverse(
            "learning:quiz-attempt",
            kwargs={"attempt_id": form.cleaned_data["attempt_id"]},
        )
        + "?saved=answer-submitted"
    )


@require_http_methods(["POST"])
def quiz_submit(request: HttpRequest, attempt_id):
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request)
    form = QuizSubmitForm(request.POST)
    if not form.is_valid():
        return _no_store(HttpResponse("提交请求不合法。", status=422))
    try:
        submit_quiz_attempt(
            account_id=request.account_id,
            attempt_id=attempt_id,
            request_id=form.cleaned_data["request_id"],
        )
    except LearningCommandError as error:
        return _no_store(
            HttpResponse(
                error.safe_message, status=409 if "conflict" in error.code else 422
            )
        )
    return redirect(
        reverse("learning:quiz-attempt", kwargs={"attempt_id": attempt_id})
        + "?saved=submitted"
    )


@require_http_methods(["POST"])
def quiz_assess(request: HttpRequest, response_id):
    if not is_active_account(getattr(request, "account_id", None)):
        return _login_required(request)
    form = QuizAssessmentForm(request.POST)
    if not form.is_valid():
        return _no_store(HttpResponse("自评请求不合法。", status=422))
    try:
        assess_quiz_short_answer(
            account_id=request.account_id,
            attempt_id=form.cleaned_data["attempt_id"],
            response_id=response_id,
            expected_version=form.cleaned_data["expected_version"],
            request_id=form.cleaned_data["request_id"],
            self_assessment=form.cleaned_data["self_assessment"],
        )
    except LearningCommandError as error:
        return _no_store(
            HttpResponse(
                error.safe_message, status=409 if "conflict" in error.code else 422
            )
        )
    return redirect(
        reverse(
            "learning:quiz-attempt",
            kwargs={"attempt_id": form.cleaned_data["attempt_id"]},
        )
        + "?saved=assessment"
    )


__all__ = [
    "quiz_assess",
    "quiz_attempt",
    "quiz_index",
    "quiz_save_response",
    "quiz_submit_response",
    "quiz_submit",
]
