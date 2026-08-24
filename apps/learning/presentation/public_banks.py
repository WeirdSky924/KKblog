from dataclasses import dataclass

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.learning.public import (
    PublicQuestionBankFilterError,
    PublicQuestionBankFilters,
    PublicQuestionBankSort,
    QuestionBankNotFound,
    public_question_bank_detail,
    public_question_bank_filter_options,
    public_question_bank_page,
)
from apps.media.public import RenderingError, render_markdown

from .public_forms import PublicQuestionBankFilterForm


@dataclass(frozen=True, slots=True)
class RenderedPublicQuestion:
    source: object
    stem_html: str
    explanation_html: str


def _page_number(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return parsed if parsed >= 1 else 1


def _page_query(request, page: int) -> str:
    values = request.GET.copy()
    values["page"] = str(page)
    if not values.get("sort"):
        values["sort"] = PublicQuestionBankSort.LATEST
    return values.urlencode()


@require_GET
def question_bank_list(request):
    options = public_question_bank_filter_options()
    bound = bool(request.GET)
    form = PublicQuestionBankFilterForm(
        request.GET if bound else None,
        options=options,
        initial={"sort": PublicQuestionBankSort.LATEST},
    )
    status = 200
    if bound and form.is_valid():
        try:
            filters = form.filters(page=_page_number(request.GET.get("page")))
        except (ValueError, PublicQuestionBankFilterError):
            filters = PublicQuestionBankFilters()
            status = 422
    elif bound:
        filters = PublicQuestionBankFilters()
        status = 422
    else:
        filters = PublicQuestionBankFilters()
    try:
        page = public_question_bank_page(filters=filters)
    except PublicQuestionBankFilterError:
        page = public_question_bank_page(filters=PublicQuestionBankFilters())
        status = 422
    return render(
        request,
        "learning/public/question_bank_list.html",
        {
            "bank_page": page,
            "filter_form": form,
            "filter_options": options,
            "previous_query": (
                _page_query(request, page.page_number - 1) if page.has_previous else ""
            ),
            "next_query": (
                _page_query(request, page.page_number + 1) if page.has_next else ""
            ),
        },
        status=status,
    )


@require_GET
def question_bank_detail(request, bank_id):
    try:
        detail = public_question_bank_detail(bank_id=bank_id)
        questions = tuple(
            RenderedPublicQuestion(
                source=question,
                stem_html=render_markdown(question.stem_markdown).html,
                explanation_html=render_markdown(question.explanation_markdown).html,
            )
            for question in detail.questions
        )
    except (QuestionBankNotFound, RenderingError):
        raise Http404 from None
    return render(
        request,
        "learning/public/question_bank_detail.html",
        {"bank": detail, "rendered_questions": questions},
    )


__all__ = ["question_bank_detail", "question_bank_list"]
