from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.moderation.public import (
    ArticleCaseError,
    create_article_moderation_case,
    restore_article_moderation_case,
    review_article_appeal,
)


def _status(code: str) -> int:
    if code in {
        "moderation.article_action_not_allowed.v1",
        "moderation.article_appeal_forbidden.v1",
        "moderation.network_restricted.v1",
    }:
        return 403
    if code in {
        "moderation.article_appeal_unavailable.v1",
        "moderation.article_case_unavailable.v1",
    }:
        return 404
    if code in {
        "moderation.article_case_state_conflict.v1",
        "moderation.article_final_review_state_conflict.v1",
    }:
        return 409
    return 422


def _error(exc: ArticleCaseError) -> JsonResponse:
    response = JsonResponse(
        {"code": exc.code, "error": exc.safe_message},
        status=_status(exc.code),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _context(request) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


@require_POST
def create_article_case_action(request, article_id: str) -> JsonResponse:
    try:
        result = create_article_moderation_case(
            actor_id=getattr(request, "account_id", None),
            article_id=article_id,
            action=request.POST.get("action", ""),
            reason=request.POST.get("reason", ""),
            **_context(request),
        )
    except ArticleCaseError as exc:
        return _error(exc)
    response = JsonResponse(
        {
            "case_id": result.case_id,
            "article_id": result.article_id,
            "action": result.action,
            "state": result.state,
            "article_changed": result.article_changed,
        },
        status=201,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@require_POST
def restore_article_case_action(request, case_id: str) -> JsonResponse:
    try:
        result = restore_article_moderation_case(
            actor_id=getattr(request, "account_id", None),
            case_id=case_id,
            **_context(request),
        )
    except ArticleCaseError as exc:
        return _error(exc)
    response = JsonResponse(
        {
            "case_id": result.case_id,
            "article_id": result.article_id,
            "state": result.state,
            "article_changed": result.article_changed,
            "recovery_status": result.recovery_status,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@require_POST
def review_article_appeal_action(request, appeal_id: str) -> JsonResponse:
    try:
        result = review_article_appeal(
            actor_id=getattr(request, "account_id", None),
            appeal_id=appeal_id,
            outcome=request.POST.get("outcome", ""),
            decision_reason=request.POST.get("decision_reason", ""),
            **_context(request),
        )
    except ArticleCaseError as exc:
        return _error(exc)
    response = JsonResponse(
        {
            "appeal_id": result.appeal_id,
            "case_id": result.case_id,
            "article_id": result.article_id,
            "state": result.state,
            "article_changed": result.article_changed,
            "recovery_status": result.recovery_status,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response
