from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .presentation import ArticleAppealForm
from .public import (
    ArticleCaseError,
    appeal_article_action,
    stage_article_appeal_evidence,
)


def _status(code: str) -> int:
    if code in {
        "moderation.article_action_not_allowed.v1",
        "moderation.article_appeal_forbidden.v1",
        "moderation.network_restricted.v1",
    }:
        return 403
    if code == "moderation.article_appeal_unavailable.v1":
        return 404
    if code == "moderation.article_appeal_state_conflict.v1":
        return 409
    return 422


def _json(payload: dict, *, status: int) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _error(exc: ArticleCaseError) -> JsonResponse:
    return _json(
        {"code": exc.code, "error": exc.safe_message},
        status=_status(exc.code),
    )


@require_POST
def create_article_appeal(request, case_id: str) -> JsonResponse:
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return _json({"error": "请先登录。"}, status=403)
    form = ArticleAppealForm(request.POST)
    if not form.is_valid():
        return _json({"errors": form.errors.get_json_data()}, status=422)
    try:
        result = appeal_article_action(
            actor_id=actor_id,
            case_id=case_id,
            statement=form.cleaned_data["statement"],
            evidence_refs=form.evidence_refs,
            client_ip=request.client_ip,
        )
    except ArticleCaseError as exc:
        return _error(exc)
    return _json(
        {
            "appeal_id": result.appeal_id,
            "case_id": result.case_id,
            "state": result.state,
            "evidence_count": result.evidence_count,
        },
        status=201,
    )


@require_POST
def upload_article_appeal_evidence(request, case_id: str) -> JsonResponse:
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return _json({"error": "请先登录。"}, status=403)
    uploaded = request.FILES.get("file")
    if uploaded is None or len(request.FILES) != 1:
        return _json({"error": "请选择一张图片后重试。"}, status=422)
    try:
        result = stage_article_appeal_evidence(
            actor_id=actor_id,
            case_id=case_id,
            client_ip=request.client_ip,
            original_name=uploaded.name,
            declared_content_type=uploaded.content_type or "",
            chunks=uploaded.chunks(),
        )
    except ArticleCaseError as exc:
        return _error(exc)
    return _json(
        {"asset_id": result.asset_id, "evidence_ref": result.evidence_ref},
        status=201,
    )
