from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.accounts.public import is_administrator
from apps.administration.forms.moderation import (
    AdminArticleFilterForm,
    ArticleActionConfirmationForm,
    ArticleAppealReviewConfirmationForm,
    ArticleDirectRestoreConfirmationForm,
    ArticleRestoreConfirmationForm,
)
from apps.administration.presentation.moderation import admin_article_rows
from apps.administration.views.article_preview import article_preview_context
from apps.content.public import (
    ArticleDeletionError,
    ArticleNotFound,
    admin_article_item,
    admin_article_page,
    restore_deleted_article,
)
from apps.media.public import MediaTargetType, target_binding_snapshot
from apps.moderation.public import (
    ArticleCaseError,
    ArticleCaseNotFound,
    article_case_detail,
    article_case_list,
    create_article_moderation_case,
    restore_article_moderation_case,
    review_article_appeal,
)


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


def _target(request: HttpRequest, kind: str, identity: str):
    if kind in {"hide", "delete"}:
        try:
            item = admin_article_item(
                actor_id=request.account_id,
                article_id=identity,
            )
        except (LookupError, PermissionError):
            raise Http404 from None
        if item.author_id == request.account_id:
            raise Http404
        if kind == "hide" and not item.can_hide:
            raise Http404
        if kind == "delete" and not item.can_delete:
            raise Http404
        return {"article": item, "case": None}
    if kind == "restore-direct":
        try:
            item = admin_article_item(
                actor_id=request.account_id,
                article_id=identity,
            )
        except (LookupError, PermissionError):
            raise Http404 from None
        if not item.can_restore_deleted:
            raise Http404
        return {"article": item, "case": None}
    try:
        case = article_case_detail(
            actor_id=request.account_id,
            case_id=identity,
        )
        item = admin_article_item(
            actor_id=request.account_id,
            article_id=case.article_id,
        )
    except (ArticleCaseNotFound, LookupError, PermissionError):
        raise Http404 from None
    if kind == "restore" and case.state != "ACTIVE":
        raise Http404
    if kind.startswith("appeal-") and (case.state != "APPEALED" or case.appeal is None):
        raise Http404
    return {"article": item, "case": case}


def _confirmation(request: HttpRequest):
    kind = request.GET.get("confirm_action", "")
    if not kind:
        return "", None, None
    if kind in {"hide", "delete"}:
        target = _target(request, kind, request.GET.get("article_id", ""))
        form = ArticleActionConfirmationForm(
            initial={
                "article_id": target["article"].id,
                "moderation_action": kind.upper(),
                "confirm": "article_action",
            }
        )
    elif kind == "restore":
        target = _target(request, kind, request.GET.get("case_id", ""))
        form = ArticleRestoreConfirmationForm(
            initial={
                "case_id": target["case"].id,
                "confirm": "article_restore",
            }
        )
    elif kind == "restore-direct":
        target = _target(request, kind, request.GET.get("article_id", ""))
        form = ArticleDirectRestoreConfirmationForm(
            initial={
                "article_id": target["article"].id,
                "expected_row_version": target["article"].row_version,
                "confirm": "article_direct_restore",
            }
        )
    elif kind in {"appeal-granted", "appeal-rejected"}:
        target = _target(request, kind, request.GET.get("case_id", ""))
        form = ArticleAppealReviewConfirmationForm(
            initial={
                "case_id": target["case"].id,
                "appeal_id": target["case"].appeal.id,
                "outcome": kind.removeprefix("appeal-").upper(),
                "confirm": "article_appeal_review",
            }
        )
    else:
        raise Http404
    return kind, target, form


def _dialog(kind: str, target, form) -> dict[str, object]:
    if not kind or target is None or form is None:
        return {}
    title = target["article"].title
    base = {
        "return_url": f"{reverse('admin:articles')}#article-list",
        "return_focus_id": f"article-{kind}-{target['article'].id}",
    }
    if kind == "hide":
        return base | {
            "title": "确认隐藏这篇已发布文章？",
            "description": f"《{title}》将从所有读者入口隐藏，但原可见性会保留用于恢复。",
            "details": "作者可申诉一次；动作会永久审计并发送站内通知。",
            "action": "article_action",
            "label": "确认隐藏",
            "field": form["reason"],
        }
    if kind == "delete":
        return base | {
            "title": "确认删除这篇文章？",
            "description": f"《{title}》将进入既有删除冷静期，期间可由管理员恢复。",
            "details": "管理员不能代为编辑、发布、排期或修改文章设置。",
            "action": "article_action",
            "label": "确认删除",
            "field": form["reason"],
        }
    if kind == "restore":
        return base | {
            "title": "确认恢复这篇文章？",
            "description": f"《{title}》将恢复到管理员操作前的精确状态。",
            "details": "恢复会永久审计并通知作者。",
            "action": "article_restore",
            "label": "确认恢复",
            "field": None,
        }
    if kind == "restore-direct":
        return base | {
            "title": "确认恢复这篇文章？",
            "description": f"《{title}》仍在删除冷静期内，将恢复到删除前的状态。",
            "details": "恢复会永久审计并通知作者；冷静期结束后将无法恢复。",
            "action": "article_direct_restore",
            "label": "确认恢复",
            "field": None,
        }
    outcome = "准许" if kind == "appeal-granted" else "驳回"
    return base | {
        "title": f"确认{outcome}文章申诉？",
        "description": f"《{title}》的申诉只复审一次，本次结果为终局。",
        "details": "准许会恢复原状态；恢复失败会保留案件错误状态供追踪。",
        "action": "article_appeal_review",
        "label": f"确认{outcome}",
        "field": form["decision_reason"],
        "return_url": (
            f"{reverse('admin:articles')}?case_detail={target['case'].id}"
            "#article-case-detail"
        ),
    }


def _preview_return_url(request: HttpRequest) -> str:
    params = request.GET.copy()
    for key in ("detail", "revision", "revision_id"):
        params.pop(key, None)
    target = reverse("admin:articles")
    if params:
        target = f"{target}?{params.urlencode()}"
    return f"{target}#article-list"


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    confirmation_kind: str = "",
    confirmation_target=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    filter_form = AdminArticleFilterForm(request.GET)
    if filter_form.is_valid():
        query = filter_form.cleaned_data["q"]
        state = filter_form.cleaned_data["state"]
    else:
        query = state = ""
        status = 422
    try:
        article_page = admin_article_page(
            actor_id=request.account_id,
            query=query,
            state=state,
            page=filter_form.cleaned_data.get("page") or 1,
            page_size=20,
        )
        cases = article_case_list(
            actor_id=request.account_id,
            article_ids=tuple(article.id for article in article_page.items),
            limit=200,
        )
    except PermissionError:
        raise PermissionDenied from None
    except ValueError as exc:
        article_page = admin_article_page(
            actor_id=request.account_id, query="", state="", page=1, page_size=20
        )
        cases = ()
        page_error = str(exc)
        status = 422

    preview = {}
    detail_revision = request.GET.get("revision", "working")
    detail_id = request.GET.get("detail", "")
    if detail_id:
        try:
            preview = article_preview_context(
                request,
                article_id=detail_id,
                revision=detail_revision,
                revision_id=request.GET.get("revision_id", ""),
            )
        except (ArticleNotFound, LookupError):
            raise Http404 from None

    selected_case = None
    selected_case_article = None
    case_evidence = ()
    case_id = request.GET.get("case_detail", "")
    if case_id:
        try:
            selected_case = article_case_detail(
                actor_id=request.account_id,
                case_id=case_id,
            )
            selected_case_article = admin_article_item(
                actor_id=request.account_id,
                article_id=selected_case.article_id,
            )
        except (ArticleCaseNotFound, LookupError, PermissionError):
            raise Http404 from None
        if selected_case.appeal is not None:
            case_evidence = tuple(
                item
                for item in target_binding_snapshot(
                    target_type=MediaTargetType.ARTICLE_APPEAL,
                    target_id=selected_case.appeal.id,
                )
                if item.state == "ACTIVE"
            )

    response = render(
        request,
        "administration/articles.html",
        {
            "rows": admin_article_rows(
                articles=article_page.items,
                cases=cases,
                actor_id=request.account_id,
            ),
            "article_page": article_page,
            "pagination_query": urlencode({"q": query, "state": state}),
            "filter_form": filter_form,
            **preview,
            "preview_dialog_open": bool(preview),
            "preview_return_url": _preview_return_url(request),
            "selected_case": selected_case,
            "selected_case_article": selected_case_article,
            "case_evidence": case_evidence,
            "confirmation_kind": confirmation_kind,
            "confirmation_form": confirmation_form,
            "dialog": _dialog(
                confirmation_kind,
                confirmation_target,
                confirmation_form,
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _service_error(request, *, kind: str, target, form, exc) -> HttpResponse:
    field = getattr(exc, "field", None)
    if field == "action":
        field = "moderation_action"
    form.add_error(field if field in form.fields else None, exc.safe_message)
    status = 409 if "conflict" in exc.code else 422
    if "not_allowed" in exc.code or "forbidden" in exc.code:
        status = 403
    return _render(
        request,
        status=status,
        confirmation_kind=kind,
        confirmation_target=target,
        confirmation_form=form,
    )


def _invalid_confirmation(request, *, kind: str, identity: str, form, message: str):
    try:
        target = _target(request, kind, identity)
    except Http404:
        return _render(request, status=422, page_error=message)
    return _render(
        request,
        status=422,
        confirmation_kind=kind,
        confirmation_target=target,
        confirmation_form=form,
    )


def _post(request: HttpRequest) -> HttpResponse:
    action = request.POST.get("action", "")
    if action == "article_action":
        form = ArticleActionConfirmationForm(request.POST)
        if not form.is_valid():
            raw_action = request.POST.get("moderation_action", "").lower()
            if raw_action not in {"hide", "delete"}:
                return _render(request, status=422, page_error="请重新确认文章操作。")
            return _invalid_confirmation(
                request,
                kind=raw_action,
                identity=request.POST.get("article_id", ""),
                form=form,
                message="请重新确认文章操作。",
            )
        kind = form.cleaned_data["moderation_action"].lower()
        target = _target(request, kind, form.cleaned_data["article_id"])
        try:
            create_article_moderation_case(
                actor_id=request.account_id,
                article_id=form.cleaned_data["article_id"],
                action=form.cleaned_data["moderation_action"],
                reason=form.cleaned_data["reason"],
                **_meta(request),
            )
        except ArticleCaseError as exc:
            return _service_error(request, kind=kind, target=target, form=form, exc=exc)
        saved = kind
    elif action == "article_restore":
        form = ArticleRestoreConfirmationForm(request.POST)
        if not form.is_valid():
            return _invalid_confirmation(
                request,
                kind="restore",
                identity=request.POST.get("case_id", ""),
                form=form,
                message="请重新确认文章恢复。",
            )
        target = _target(request, "restore", form.cleaned_data["case_id"])
        try:
            restore_article_moderation_case(
                actor_id=request.account_id,
                case_id=form.cleaned_data["case_id"],
                **_meta(request),
            )
        except ArticleCaseError as exc:
            return _service_error(
                request, kind="restore", target=target, form=form, exc=exc
            )
        saved = "restored"
    elif action == "article_direct_restore":
        form = ArticleDirectRestoreConfirmationForm(request.POST)
        if not form.is_valid():
            return _invalid_confirmation(
                request,
                kind="restore-direct",
                identity=request.POST.get("article_id", ""),
                form=form,
                message="请重新确认文章恢复。",
            )
        target = _target(request, "restore-direct", form.cleaned_data["article_id"])
        try:
            restore_deleted_article(
                actor_id=request.account_id,
                article_id=form.cleaned_data["article_id"],
                expected_row_version=form.cleaned_data["expected_row_version"],
                trace_code=getattr(request, "trace_code", ""),
                client_ip=request.client_ip,
            )
        except ArticleDeletionError as exc:
            form.add_error(None, exc.safe_message)
            status = 409 if exc.code == "content.edit_conflict.v1" else 422
            if exc.code == "content.article_restore_not_allowed.v1":
                status = 403
            return _render(
                request,
                status=status,
                confirmation_kind="restore-direct",
                confirmation_target=target,
                confirmation_form=form,
            )
        saved = "restored"
    elif action == "article_appeal_review":
        form = ArticleAppealReviewConfirmationForm(request.POST)
        if not form.is_valid():
            raw_outcome = request.POST.get("outcome", "").lower()
            if raw_outcome not in {"granted", "rejected"}:
                return _render(
                    request,
                    status=422,
                    page_error="请重新确认文章申诉复审。",
                )
            return _invalid_confirmation(
                request,
                kind=f"appeal-{raw_outcome}",
                identity=request.POST.get("case_id", ""),
                form=form,
                message="请重新确认文章申诉复审。",
            )
        kind = f"appeal-{form.cleaned_data['outcome'].lower()}"
        target = _target(request, kind, form.cleaned_data["case_id"])
        try:
            review_article_appeal(
                actor_id=request.account_id,
                appeal_id=form.cleaned_data["appeal_id"],
                outcome=form.cleaned_data["outcome"],
                decision_reason=form.cleaned_data["decision_reason"],
                **_meta(request),
            )
        except ArticleCaseError as exc:
            return _service_error(request, kind=kind, target=target, form=form, exc=exc)
        saved = "appeal-reviewed"
    else:
        return _render(request, status=422, page_error="文章管理操作无效。")
    if saved == "appeal-reviewed":
        return redirect(
            f"{reverse('admin:articles')}?saved={saved}"
            f"&case_detail={form.cleaned_data['case_id']}#article-case-detail"
        )
    return redirect(f"{reverse('admin:articles')}?saved={saved}")


def articles(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "POST":
        return _post(request)
    kind, target, form = _confirmation(request)
    return _render(
        request,
        confirmation_kind=kind,
        confirmation_target=target,
        confirmation_form=form,
    )


__all__ = ["articles"]
