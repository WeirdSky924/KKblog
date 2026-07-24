from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.comments.public import (
    CommentReportTargetError,
    DiscussionTargetType,
    reportable_comment_target,
)
from apps.core.ids import normalize_ulid

from .presentation import ReportForm
from .services import ReportSubmissionError, create_report, stage_report_evidence


def _comment_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise Http404 from None


def _status(code: str) -> int:
    if code in {
        "moderation.login_required.v1",
        "moderation.account_unavailable.v1",
        "moderation.network_restricted.v1",
    }:
        return 403
    if code == "moderation.target_unavailable.v1":
        return 404
    if code == "moderation.report_duplicate.v1":
        return 409
    return 422


def _noun(*, comment_id: str, actor_id) -> str:
    try:
        target = reportable_comment_target(
            comment_id=comment_id,
            actor_id=actor_id,
        )
    except CommentReportTargetError:
        raise Http404 from None
    return "留言" if target.target_type is DiscussionTargetType.GUESTBOOK else "评论"


def _dialog_response(
    request,
    *,
    comment_id: str,
    comment_noun: str,
    form: ReportForm,
    status: int,
):
    response = render(
        request,
        "moderation/partials/report_dialog.html",
        {
            "comment_id": comment_id,
            "comment_noun": comment_noun,
            "report_form": form,
            "report_url": reverse(
                "moderation:report-create",
                kwargs={"comment_id": comment_id},
            ),
            "evidence_upload_url": reverse(
                "moderation:report-evidence-upload",
                kwargs={"comment_id": comment_id},
            ),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def confirm_report(request, comment_id):
    identity = _comment_id(comment_id)
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return HttpResponse(status=403)
    return _dialog_response(
        request,
        comment_id=identity,
        comment_noun=_noun(comment_id=identity, actor_id=actor_id),
        form=ReportForm(comment_id=identity),
        status=200,
    )


@require_POST
def create_comment_report(request, comment_id):
    identity = _comment_id(comment_id)
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return HttpResponse(status=403)
    comment_noun = _noun(comment_id=identity, actor_id=actor_id)
    form = ReportForm(request.POST, comment_id=identity)
    if not form.is_valid():
        return _dialog_response(
            request,
            comment_id=identity,
            comment_noun=comment_noun,
            form=form,
            status=422,
        )
    try:
        result = create_report(
            actor_id=actor_id,
            comment_id=identity,
            reason=form.cleaned_data["reason"],
            description=form.cleaned_data["description"],
            evidence_refs=form.evidence_refs,
            client_ip=request.client_ip,
        )
    except ReportSubmissionError as exc:
        field = exc.field if exc.field in {"reason", "description"} else None
        form.add_error(field, exc.safe_message)
        return _dialog_response(
            request,
            comment_id=identity,
            comment_noun=comment_noun,
            form=form,
            status=_status(exc.code),
        )
    response = render(
        request,
        "moderation/partials/report_success_dialog.html",
        {
            "comment_id": identity,
            "comment_noun": comment_noun,
            "evidence_count": result.evidence_count,
        },
        status=201,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_POST
def upload_report_evidence(request, comment_id):
    identity = _comment_id(comment_id)
    actor_id = getattr(request, "account_id", None)
    if actor_id is None:
        return HttpResponse(status=403)
    uploaded = request.FILES.get("file")
    if uploaded is None or len(request.FILES) != 1:
        context = {"upload_error": "请选择一张图片后重试。"}
        status = 422
    else:
        try:
            result = stage_report_evidence(
                actor_id=actor_id,
                comment_id=identity,
                client_ip=request.client_ip,
                original_name=uploaded.name,
                declared_content_type=uploaded.content_type or "",
                chunks=uploaded.chunks(),
            )
        except ReportSubmissionError as exc:
            context = {
                "upload_error": exc.safe_message,
                "original_name": uploaded.name,
            }
            status = _status(exc.code)
        else:
            context = {"upload": result}
            status = 201
    response = render(
        request,
        "moderation/partials/evidence_upload_result.html",
        context,
        status=status,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
