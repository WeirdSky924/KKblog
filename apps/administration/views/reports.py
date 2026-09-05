from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.accounts.public import (
    AccountAdministrationQueryError,
    admin_account_detail,
    is_administrator,
)
from apps.administration.forms.moderation import (
    AdminReportFilterForm,
    ReportFinalReviewConfirmationForm,
    ReportReviewConfirmationForm,
)
from apps.comments.public import AdminCommentNotFound, admin_comment_detail
from apps.media.public import MediaTargetType, target_binding_snapshot
from apps.moderation.public import (
    AdminReportNotFound,
    ReportAppealError,
    ReportReviewError,
    admin_report_detail,
    admin_report_list,
    finalize_report_appeal,
    report_recovery_snapshot_access,
    review_report,
)


def _detail(request: HttpRequest, report_id: str):
    try:
        return admin_report_detail(
            actor_id=request.account_id,
            report_id=report_id,
        )
    except (AdminReportNotFound, PermissionError):
        raise Http404 from None


def _account(request: HttpRequest, account_id):
    if account_id is None:
        return None
    try:
        return admin_account_detail(
            actor_id=request.account_id,
            account_id=account_id,
        )
    except AccountAdministrationQueryError:
        return None


def _confirmation(request: HttpRequest):
    kind = request.GET.get("confirm_action", "")
    if not kind:
        return "", None, None
    if kind not in {
        "review-upheld",
        "review-rejected",
        "final-upheld",
        "final-rejected",
    }:
        raise Http404
    detail = _detail(request, request.GET.get("report_id", ""))
    if kind.startswith("review-"):
        if detail.state != "PENDING":
            raise Http404
        form = ReportReviewConfirmationForm(
            initial={
                "report_id": detail.id,
                "outcome": kind.removeprefix("review-").upper(),
                "confirm": "report_review",
            }
        )
    else:
        if detail.state != "APPEAL_PENDING" or detail.appeal is None:
            raise Http404
        form = ReportFinalReviewConfirmationForm(
            initial={
                "report_id": detail.id,
                "outcome": kind.removeprefix("final-").upper(),
                "confirm": "report_final_review",
            }
        )
    return kind, detail, form


def _dialog(kind: str, detail, form) -> dict[str, object]:
    if not kind or detail is None or form is None:
        return {}
    final = kind.startswith("final-")
    upheld = kind.endswith("upheld")
    outcome = "成立" if upheld else "驳回"
    return {
        "title": f"确认{'终局复审' if final else '初审'}{outcome}？",
        "description": (
            f"举报 {detail.id} 将进入"
            f"{'不可再次申诉的终局状态' if final else '已完成初审状态'}。"
        ),
        "details": (
            "终局复审会按原初审结果决定删除或恢复评论，并销毁不再需要的恢复快照。"
            if final
            else "成立时评论立即显示删除占位并保留受限恢复快照；举报人身份不会进入被举报方通知。"
        ),
        "action": "report_final_review" if final else "report_review",
        "label": f"确认{outcome}",
        "field": form["decision_reason"],
        "return_focus_id": f"report-{kind}-{detail.id}",
        "return_url": f"{reverse('admin:reports')}?detail={detail.id}#report-detail",
    }


def _evidence(target_type: str, target_id: str) -> tuple:
    return tuple(
        item
        for item in target_binding_snapshot(
            target_type=target_type,
            target_id=target_id,
        )
        if item.state == "ACTIVE"
    )


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    confirmation_kind: str = "",
    confirmation_detail=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    filter_form = AdminReportFilterForm(request.GET)
    if filter_form.is_valid():
        state = filter_form.cleaned_data["state"]
    else:
        state = ""
        status = 422
    try:
        report_page = admin_report_list(
            actor_id=request.account_id,
            state=state,
            page=filter_form.cleaned_data.get("page") or 1,
            page_size=20,
        )
    except PermissionError:
        raise PermissionDenied from None
    except ValueError as exc:
        report_page = admin_report_list(
            actor_id=request.account_id, state="", page=1, page_size=20
        )
        page_error = str(exc)
        status = 422

    detail = None
    target_comment = None
    reporter = None
    reported_author = None
    report_evidence = ()
    appeal_evidence = ()
    recovery_snapshot = None
    detail_id = request.GET.get("detail", "")
    if detail_id:
        detail = _detail(request, detail_id)
        reporter = _account(request, detail.reporter_id)
        reported_author = _account(request, detail.reported_author_id)
        try:
            target_comment = admin_comment_detail(
                actor_id=request.account_id,
                comment_id=detail.target_comment_id,
            )
        except AdminCommentNotFound:
            target_comment = None
        report_evidence = _evidence(MediaTargetType.REPORT, detail.id)
        if detail.appeal is not None:
            appeal_evidence = _evidence(
                MediaTargetType.REPORT_APPEAL,
                detail.appeal.id,
            )
        recovery_snapshot = report_recovery_snapshot_access(
            actor_id=request.account_id,
            report_id=detail.id,
        )

    response = render(
        request,
        "administration/reports.html",
        {
            "rows": report_page.items,
            "report_page": report_page,
            "pagination_query": urlencode({"state": state}),
            "filter_form": filter_form,
            "detail": detail,
            "target_comment": target_comment,
            "reporter": reporter,
            "reported_author": reported_author,
            "report_evidence": report_evidence,
            "appeal_evidence": appeal_evidence,
            "recovery_snapshot": recovery_snapshot,
            "confirmation_kind": confirmation_kind,
            "confirmation_form": confirmation_form,
            "dialog": _dialog(
                confirmation_kind,
                confirmation_detail,
                confirmation_form,
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _service_error(request, *, kind: str, detail, form, exc) -> HttpResponse:
    field = getattr(exc, "field", None)
    form.add_error(field if field in form.fields else None, exc.safe_message)
    status = 409 if "conflict" in exc.code else 422
    if "forbidden" in exc.code or "restricted" in exc.code:
        status = 403
    return _render(
        request,
        status=status,
        confirmation_kind=kind,
        confirmation_detail=detail,
        confirmation_form=form,
    )


def _invalid_confirmation(request, *, kind: str, report_id: str, form, message: str):
    try:
        detail = _detail(request, report_id)
    except Http404:
        return _render(request, status=422, page_error=message)
    return _render(
        request,
        status=422,
        confirmation_kind=kind,
        confirmation_detail=detail,
        confirmation_form=form,
    )


def _post(request: HttpRequest) -> HttpResponse:
    action = request.POST.get("action", "")
    if action == "report_review":
        form = ReportReviewConfirmationForm(request.POST)
        if not form.is_valid():
            raw_outcome = request.POST.get("outcome", "").lower()
            if raw_outcome not in {"upheld", "rejected"}:
                return _render(request, status=422, page_error="请重新确认举报初审。")
            return _invalid_confirmation(
                request,
                kind=f"review-{raw_outcome}",
                report_id=request.POST.get("report_id", ""),
                form=form,
                message="请重新确认举报初审。",
            )
        detail = _detail(request, form.cleaned_data["report_id"])
        kind = f"review-{form.cleaned_data['outcome'].lower()}"
        try:
            review_report(
                actor_id=request.account_id,
                report_id=detail.id,
                outcome=form.cleaned_data["outcome"],
                decision_reason=form.cleaned_data["decision_reason"],
                client_ip=request.client_ip,
                trace_code=getattr(request, "trace_code", ""),
            )
        except ReportReviewError as exc:
            return _service_error(request, kind=kind, detail=detail, form=form, exc=exc)
        saved = "reviewed"
    elif action == "report_final_review":
        form = ReportFinalReviewConfirmationForm(request.POST)
        if not form.is_valid():
            raw_outcome = request.POST.get("outcome", "").lower()
            if raw_outcome not in {"upheld", "rejected"}:
                return _render(
                    request, status=422, page_error="请重新确认举报终局复审。"
                )
            return _invalid_confirmation(
                request,
                kind=f"final-{raw_outcome}",
                report_id=request.POST.get("report_id", ""),
                form=form,
                message="请重新确认举报终局复审。",
            )
        detail = _detail(request, form.cleaned_data["report_id"])
        kind = f"final-{form.cleaned_data['outcome'].lower()}"
        try:
            finalize_report_appeal(
                actor_id=request.account_id,
                report_id=detail.id,
                outcome=form.cleaned_data["outcome"],
                decision_reason=form.cleaned_data["decision_reason"],
                client_ip=request.client_ip,
                trace_code=getattr(request, "trace_code", ""),
            )
        except ReportAppealError as exc:
            return _service_error(request, kind=kind, detail=detail, form=form, exc=exc)
        saved = "finalized"
    else:
        return _render(request, status=422, page_error="举报管理操作无效。")
    return redirect(f"{reverse('admin:reports')}?saved={saved}&detail={detail.id}")


def reports(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "POST":
        return _post(request)
    kind, detail, form = _confirmation(request)
    return _render(
        request,
        confirmation_kind=kind,
        confirmation_detail=detail,
        confirmation_form=form,
    )


__all__ = ["reports"]
