from datetime import date, datetime
from hashlib import sha256
from uuid import UUID

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.learning.public import (
    PublicQuestionBankFilterError,
    PublicQuestionBankFilterOptions,
    QuestionBankNotFound,
    RateLimitDecision,
    RateLimiterUnavailable,
    consume_api_rate_limit,
    public_question_bank_detail,
    public_question_bank_filter_options,
    public_question_bank_page,
    question_bank_api_configuration,
)

from .public_forms import PublicQuestionBankFilterForm

API_SCHEMA_VERSION = 1


def _json(payload: dict, *, status: int, no_store: bool = False) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    if no_store:
        response.headers["Cache-Control"] = "no-store"
    return response


def _error(code: str, message: str, *, status: int) -> JsonResponse:
    return _json(
        {
            "schema_version": API_SCHEMA_VERSION,
            "error": {"code": code, "message": message},
        },
        status=status,
        no_store=True,
    )


def _cors(response, request, configuration):
    origin = request.headers.get("Origin", "").strip()
    if origin and origin in configuration.cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS":
            response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
            response.headers["Access-Control-Max-Age"] = "600"
    return response


def _rate_headers(response, decision: RateLimitDecision | None):
    if decision is None:
        return response
    response.headers["RateLimit-Limit"] = str(decision.limit)
    response.headers["RateLimit-Remaining"] = str(decision.remaining)
    response.headers["RateLimit-Reset"] = str(decision.reset_seconds)
    if decision.retry_after:
        response.headers["Retry-After"] = str(decision.retry_after)
    return response


def _finish(response, request, configuration, decision=None):
    return _cors(_rate_headers(response, decision), request, configuration)


def _prepare(request):
    configuration = question_bank_api_configuration()
    if not configuration.enabled:
        return (
            configuration,
            _finish(
                _error("api_disabled", "题库 API 尚未开启。", status=404),
                request,
                configuration,
            ),
            None,
        )
    if request.method == "OPTIONS":
        response = _finish(HttpResponse(status=204), request, configuration)
        response.headers["Allow"] = "GET, HEAD, OPTIONS"
        return configuration, response, None
    try:
        decision = consume_api_rate_limit(
            client_ip=getattr(request, "client_ip", ""),
            minute_limit=configuration.minute_limit,
            daily_limit=configuration.daily_limit,
        )
    except RateLimiterUnavailable:
        return (
            configuration,
            _finish(
                _error(
                    "rate_limiter_unavailable",
                    "题库 API 暂时不可用，请稍后重试。",
                    status=503,
                ),
                request,
                configuration,
            ),
            None,
        )
    if not decision.allowed:
        return (
            configuration,
            _finish(
                _error("rate_limited", "请求过于频繁，请稍后重试。", status=429),
                request,
                configuration,
                decision,
            ),
            decision,
        )
    return configuration, None, decision


def _success(payload, *, request, configuration, decision):
    response = _json(payload, status=200)
    etag_source = response.content + f"|config:{configuration.row_version}".encode()
    etag = f'"{sha256(etag_source).hexdigest()}"'
    response["ETag"] = etag
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponse(status=304)
        response["ETag"] = etag
    return _finish(response, request, configuration, decision)


def _value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _author(author):
    return {
        "id": str(author.account_id),
        "display_name": author.display_name,
        "avatar_url": author.avatar_url,
        "profile_url": author.profile_url,
    }


def _tag(tag):
    return {"id": str(tag.tag_id), "name": tag.name}


def _item(item):
    return {
        "bank_id": str(item.bank_id),
        "series_id": str(item.series_id),
        "title": item.title,
        "description": item.description,
        "volume_number": item.volume_number,
        "volume_count": item.volume_count,
        "author": _author(item.author),
        "visibility": item.visibility,
        "question_count": item.question_count,
        "question_types": list(item.question_types),
        "tags": [_tag(tag) for tag in item.tags],
        "coverage_state": item.coverage_state,
        "total_knowledge_points": item.total_knowledge_points,
        "covered_knowledge_points": item.covered_knowledge_points,
        "omitted_knowledge_points": item.omitted_knowledge_points,
        "completed_attempt_count": item.completed_attempt_count,
        "published_at": _value(item.published_at),
    }


def _option(option):
    return {"id": option.option_id, "text": option.text}


def _question(question):
    return {
        "logical_id": question.logical_id,
        "ordinal": question.ordinal,
        "question_type": question.question_type,
        "stem_markdown": question.stem_markdown,
        "options": [_option(option) for option in question.options],
        "correct_option_ids": list(question.correct_option_ids),
        "boolean_answer": question.boolean_answer,
        "reference_answer": question.reference_answer,
        "scoring_points": list(question.scoring_points),
        "explanation_markdown": question.explanation_markdown,
    }


def _detail(detail):
    return {
        "bank_id": str(detail.bank_id),
        "series_id": str(detail.series_id),
        "revision_id": str(detail.revision_id),
        "title": detail.title,
        "description": detail.description,
        "volume_number": detail.volume_number,
        "volume_count": detail.volume_count,
        "author": _author(detail.author),
        "question_count": detail.question_count,
        "question_types": list(detail.question_types),
        "tags": [_tag(tag) for tag in detail.tags],
        "coverage_state": detail.coverage_state,
        "total_knowledge_points": detail.total_knowledge_points,
        "covered_knowledge_points": detail.covered_knowledge_points,
        "omitted_knowledge_points": detail.omitted_knowledge_points,
        "completed_attempt_count": detail.completed_attempt_count,
        "published_at": _value(detail.published_at),
        "questions": [_question(question) for question in detail.questions],
    }


def _page_link(request, page: int) -> str | None:
    values = request.GET.copy()
    values["page"] = str(page)
    return f"{request.path}?{values.urlencode()}"


def _filters(request):
    options: PublicQuestionBankFilterOptions = public_question_bank_filter_options()
    form = PublicQuestionBankFilterForm(request.GET, options=options)
    if not form.is_valid():
        fields = sorted(form.errors.keys())
        return None, fields
    try:
        return form.filters(page=1), ()
    except (PublicQuestionBankFilterError, ValueError):
        return None, ["filters"]


@require_http_methods(["GET", "HEAD", "OPTIONS"])
def question_bank_list(request):
    configuration, early_response, decision = _prepare(request)
    if early_response is not None:
        return early_response
    filters, _invalid_fields = _filters(request)
    if filters is None:
        return _finish(
            _error("invalid_parameters", "筛选参数不合法。", status=422),
            request,
            configuration,
            decision,
        )
    try:
        page = public_question_bank_page(filters=filters)
    except PublicQuestionBankFilterError:
        return _finish(
            _error("invalid_parameters", "筛选参数不合法。", status=422),
            request,
            configuration,
            decision,
        )
    return _success(
        {
            "schema_version": API_SCHEMA_VERSION,
            "data": {
                "count": page.total_items,
                "total_pages": page.total_pages,
                "page": page.page_number,
                "page_size": page.page_size,
                "previous": (
                    _page_link(request, page.page_number - 1)
                    if page.has_previous
                    else None
                ),
                "next": (
                    _page_link(request, page.page_number + 1) if page.has_next else None
                ),
                "results": [_item(item) for item in page.items],
            },
        },
        request=request,
        configuration=configuration,
        decision=decision,
    )


@require_http_methods(["GET", "HEAD", "OPTIONS"])
def question_bank_detail(request, bank_id):
    configuration, early_response, decision = _prepare(request)
    if early_response is not None:
        return early_response
    try:
        detail = public_question_bank_detail(bank_id=bank_id)
    except (QuestionBankNotFound, ValueError, TypeError):
        return _finish(
            _error("not_found", "题库不存在。", status=404),
            request,
            configuration,
            decision,
        )
    return _success(
        {"schema_version": API_SCHEMA_VERSION, "data": _detail(detail)},
        request=request,
        configuration=configuration,
        decision=decision,
    )


__all__ = ["question_bank_detail", "question_bank_list"]
