from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.administration.forms.classification import (
    AdminTagFilterForm,
    TagActionConfirmationForm,
    TagCreateForm,
)
from apps.administration.presentation.moderation import account_label, account_labels
from apps.content.public import (
    TagCommandError,
    admin_tag_detail,
    admin_tag_item,
    admin_tag_page,
    create_tag,
    delete_tag,
    restore_tag,
    review_tag,
)

from ..presentation.feedback import feedback_count

VALID_ACTIONS = {"approve", "reject", "delete", "restore"}


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _tag(request: HttpRequest, tag_id: str):
    try:
        return admin_tag_item(actor_id=request.account_id, tag_id=tag_id)
    except (LookupError, PermissionError):
        raise Http404 from None


def _can_action(tag, kind: str) -> bool:
    return (
        (kind in {"approve", "reject"} and tag.can_review)
        or (kind == "delete" and tag.can_delete)
        or (kind == "restore" and tag.can_restore)
    )


def _confirmation(request: HttpRequest):
    kind = request.GET.get("confirm_action", "")
    if not kind:
        return "", None, None
    if kind not in VALID_ACTIONS:
        raise Http404
    tag = _tag(request, request.GET.get("tag_id", ""))
    if not _can_action(tag, kind):
        raise Http404
    form = TagActionConfirmationForm(
        initial={
            "tag_id": tag.id,
            "tag_action": kind.upper(),
            "confirm": "tag_action",
        }
    )
    return kind, tag, form


def _dialog(kind: str, tag, form) -> dict[str, object]:
    if not kind or tag is None or form is None:
        return {}
    base = {
        "return_focus_id": f"tag-{kind}-{tag.id}",
        "return_url": f"{reverse('admin:tags')}#tag-list",
        "action": "tag_action",
        "field": None,
    }
    if kind == "approve":
        return base | {
            "title": "确认通过这个待审核标签？",
            "description": f"“{tag.name}”将成为全站可用标签。",
            "details": (
                f"当前 {tag.current_article_count} 篇文章会保留关联，"
                "提议者与受影响作者将收到站内通知。"
            ),
            "label": "确认通过",
        }
    if kind == "reject":
        return base | {
            "title": "确认驳回这个待审核标签？",
            "description": f"“{tag.name}”将从所有当前文章移除。",
            "details": (
                f"本次影响 {tag.current_article_count} 篇文章，"
                "审核结果会永久审计并发送站内通知。"
            ),
            "label": "确认驳回",
        }
    if kind == "delete":
        return base | {
            "title": "确认删除这个全站标签？",
            "description": f"“{tag.name}”将从 {tag.current_article_count} 篇文章移除。",
            "details": "旧标签链接会返回空结果；关联历史会保留，供以后恢复。",
            "label": "确认删除",
        }
    return base | {
        "title": "确认恢复这个标签及历史关联？",
        "description": (
            f"“{tag.name}”有 {tag.pending_history_count} 条待恢复关联，"
            f"当前存在 {tag.open_conflict_count} 条开放冲突。"
        ),
        "details": "文章已满 10 个标签时不会静默覆盖；冲突会保留并显示，可稍后重试。",
        "label": "确认恢复",
    }


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    create_form=None,
    confirmation_kind: str = "",
    confirmation_tag=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    filter_form = AdminTagFilterForm(request.GET)
    if filter_form.is_valid():
        state = filter_form.cleaned_data["state"]
    else:
        state = ""
        status = 422
    try:
        tag_page = admin_tag_page(
            actor_id=request.account_id,
            state=state,
            page=filter_form.cleaned_data.get("page") or 1,
            page_size=20,
        )
    except PermissionError:
        raise PermissionDenied from None
    except ValueError as exc:
        tag_page = admin_tag_page(
            actor_id=request.account_id, state="", page=1, page_size=20
        )
        page_error = str(exc)
        status = 422

    detail = None
    detail_id = request.GET.get("detail", "")
    if detail_id:
        try:
            detail = admin_tag_detail(
                actor_id=request.account_id,
                tag_id=detail_id,
                history_page=_page_number(request.GET.get("history_page")),
                conflict_page=_page_number(request.GET.get("conflict_page")),
                page_size=20,
            )
        except (LookupError, PermissionError):
            raise Http404 from None

    account_ids = [
        account_id
        for item in tag_page.items
        for account_id in (item.proposed_by_id, item.reviewed_by_id)
        if account_id is not None
    ]
    if detail is not None:
        account_ids.extend(
            account_id
            for account_id in (
                detail.tag.proposed_by_id,
                detail.tag.reviewed_by_id,
            )
            if account_id is not None
        )
    labels = account_labels(tuple(account_ids))
    rows = tuple(
        {
            "tag": item,
            "history_url": (
                f"{reverse('admin:tags')}?"
                f"{urlencode({'state': state, 'detail': str(item.id)} if state else {'detail': str(item.id)})}"
            ),
            "history_trigger_id": f"tag-history-{item.id}",
            "proposer_label": (
                account_label(labels, item.proposed_by_id)
                if item.proposed_by_id is not None
                else "管理员创建"
            ),
            "reviewer_label": (
                account_label(labels, item.reviewed_by_id)
                if item.reviewed_by_id is not None
                else "尚未审核"
            ),
        }
        for item in tag_page.items
    )
    detail_proposer_label = ""
    detail_reviewer_label = ""
    if detail is not None:
        detail_proposer_label = (
            account_label(labels, detail.tag.proposed_by_id)
            if detail.tag.proposed_by_id is not None
            else "管理员创建"
        )
        detail_reviewer_label = (
            account_label(labels, detail.tag.reviewed_by_id)
            if detail.tag.reviewed_by_id is not None
            else "尚未审核"
        )
    response = render(
        request,
        "administration/tags.html",
        {
            "rows": rows,
            "tag_page": tag_page,
            "pagination_query": urlencode({"state": state}),
            "filter_form": filter_form,
            "create_form": create_form or TagCreateForm(),
            "detail": detail,
            "detail_proposer_label": detail_proposer_label,
            "detail_reviewer_label": detail_reviewer_label,
            "tag_detail_return_url": (
                f"{reverse('admin:tags')}"
                f"{('?' + urlencode({'state': state})) if state else ''}#tag-list"
            ),
            "confirmation_kind": confirmation_kind,
            "confirmation_form": confirmation_form,
            "dialog": _dialog(
                confirmation_kind,
                confirmation_tag,
                confirmation_form,
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "restored_conflicts": feedback_count(request.GET, "conflicts"),
            "tag_history_pagination_query": urlencode(
                {
                    key: value
                    for key, value in {
                        "state": state,
                        "detail": detail_id,
                    }.items()
                    if value
                }
            ),
            "tag_conflict_pagination_query": urlencode(
                {
                    key: value
                    for key, value in {
                        "state": state,
                        "detail": detail_id,
                    }.items()
                    if value
                }
            ),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _action_error(request, *, kind: str, tag, form, error) -> HttpResponse:
    form.add_error(None, error.safe_message)
    return _render(
        request,
        status=409 if error.code == "content.tag_name_conflict.v1" else 422,
        confirmation_kind=kind,
        confirmation_tag=tag,
        confirmation_form=form,
    )


def _post_create(request: HttpRequest) -> HttpResponse:
    form = TagCreateForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, create_form=form)
    try:
        create_tag(
            actor_id=request.account_id,
            name=form.cleaned_data["name"],
            **_meta(request),
        )
    except TagCommandError as error:
        form.add_error("name", error.safe_message)
        return _render(request, status=422, create_form=form)
    return redirect(f"{reverse('admin:tags')}?saved=created#tag-list")


def _post_action(request: HttpRequest) -> HttpResponse:
    form = TagActionConfirmationForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, page_error="请重新确认标签操作。")
    kind = form.cleaned_data["tag_action"].lower()
    try:
        tag = _tag(request, str(form.cleaned_data["tag_id"]))
    except Http404:
        return _render(request, status=422, page_error="标签已不存在。")
    if not _can_action(tag, kind):
        return _render(request, status=422, page_error="标签状态已变化，请刷新后重试。")

    try:
        if kind in {"approve", "reject"}:
            review_tag(
                actor_id=request.account_id,
                tag_id=tag.id,
                approved=kind == "approve",
                **_meta(request),
            )
            saved = "approved" if kind == "approve" else "rejected"
            return redirect(f"{reverse('admin:tags')}?saved={saved}#tag-list")
        if kind == "delete":
            delete_tag(
                actor_id=request.account_id,
                tag_id=tag.id,
                **_meta(request),
            )
            return redirect(f"{reverse('admin:tags')}?saved=deleted#tag-list")
        result = restore_tag(
            actor_id=request.account_id,
            tag_id=tag.id,
            **_meta(request),
        )
    except TagCommandError as error:
        return _action_error(request, kind=kind, tag=tag, form=form, error=error)
    return redirect(
        f"{reverse('admin:tags')}?saved=restored&conflicts={result.conflict_count}"
        f"&detail={tag.id}#tag-detail"
    )


def tags(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "tag_create":
            return _post_create(request)
        if action == "tag_action":
            return _post_action(request)
        return _render(request, status=422, page_error="标签管理操作无效。")
    kind, tag, form = _confirmation(request)
    return _render(
        request,
        confirmation_kind=kind,
        confirmation_tag=tag,
        confirmation_form=form,
    )


__all__ = ["tags"]
