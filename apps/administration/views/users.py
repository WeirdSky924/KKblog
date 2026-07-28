from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import (
    AccountAdministrationQueryError,
    AccountLifecycleError,
    delete_account,
    is_administrator,
    set_account_enabled,
    set_author_role,
)
from apps.administration.forms.users import (
    AccountDeletionConfirmationForm,
    AccountRoleConfirmationForm,
    AccountStatusConfirmationForm,
    AdminUserFilterForm,
)
from apps.administration.presentation.users import (
    admin_user_target,
    admin_users_presentation,
)
from apps.content.public import (
    AccountArticleDispositionError,
    apply_account_deletion_disposition,
    prepare_account_deletion_disposition,
)
from apps.operations.public import record_audit_entry


def _page(value) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _target(*, actor_id, account_id):
    try:
        return admin_user_target(actor_id=actor_id, account_id=account_id)
    except AccountAdministrationQueryError:
        raise Http404 from None


def _dialog(kind: str, target, form) -> dict[str, str]:
    if not kind or target is None or form is None:
        return {}
    display = target.account.display_name
    if kind == "role":
        enabled = str(form["enabled"].value()).lower() in {"1", "true"}
        return {
            "title": f"确认{'授予' if enabled else '撤销'}作者角色？",
            "description": (
                f"账户 {display} 将{'获得创作权限' if enabled else '失去后续创作权限，已有文章仍保留原归属'}。"
            ),
            "details": "角色变化会写入永久审计，并向该账户发送站内通知。",
            "action": "set_author",
            "label": "确认变更",
            "return_focus_id": f"account-role-{target.account.account_id}",
            "return_url": f"{reverse('admin:users')}#user-list",
        }
    if kind == "status":
        enabled = str(form["enabled"].value()).lower() in {"1", "true"}
        return {
            "title": f"确认{'启用' if enabled else '禁用'}这个账户？",
            "description": (
                f"账户 {display} {'将恢复登录；旧会话不会复活' if enabled else '的全部现有会话会立即撤销，已发布文章暂时隐藏，排期转为草稿'}。"
            ),
            "details": "禁用与启用都会永久审计，但不会向账户发送通知。",
            "action": "set_status",
            "label": f"确认{'启用' if enabled else '禁用'}",
            "return_focus_id": f"account-status-{target.account.account_id}",
            "return_url": f"{reverse('admin:users')}#user-list",
        }
    return {
        "title": "确认永久删除这个账户？",
        "description": (
            f"账户 {display} 当前拥有 {target.article_count} 篇文章；确认后账户、文章及关联私有数据会永久删除。"
        ),
        "details": "如需保留作者内容，请先取消并在导入导出中完成按作者导出；本操作不会自动创建导出。",
        "action": "delete",
        "label": "确认永久删除",
        "return_focus_id": f"account-delete-{target.account.account_id}",
        "return_url": f"{reverse('admin:users')}#user-list",
    }


def _get_confirmation(request: HttpRequest, actor_id):
    kind = request.GET.get("confirm_action", "")
    if not kind:
        return "", None, None
    target = _target(
        actor_id=actor_id,
        account_id=request.GET.get("account_id", ""),
    )
    if not target.can_manage:
        raise Http404
    if kind == "role":
        enabled = request.GET.get("enabled", "")
        if enabled not in {"0", "1"}:
            raise Http404
        form = AccountRoleConfirmationForm(
            initial={
                "account_id": target.account.account_id,
                "enabled": enabled,
                "confirm": "role",
            }
        )
    elif kind == "status":
        enabled = request.GET.get("enabled", "")
        if enabled not in {"0", "1"}:
            raise Http404
        form = AccountStatusConfirmationForm(
            initial={
                "account_id": target.account.account_id,
                "enabled": enabled,
                "confirm": "status",
            }
        )
    elif kind == "delete":
        form = AccountDeletionConfirmationForm(
            initial={
                "account_id": target.account.account_id,
                "expected_article_count": target.article_count,
                "confirm": "delete",
            }
        )
    else:
        raise Http404
    return kind, target, form


def _render(
    request: HttpRequest,
    *,
    status_code: int = 200,
    confirmation_kind: str = "",
    confirmation_target=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    filter_form = AdminUserFilterForm(request.GET)
    if filter_form.is_valid():
        keyword = filter_form.cleaned_data["q"]
        selected_status = filter_form.cleaned_data["status"]
    else:
        keyword = ""
        selected_status = ""
        status_code = 422
    try:
        presentation = admin_users_presentation(
            actor_id=request.account_id,
            keyword=keyword,
            status=selected_status,
            page=_page(request.GET.get("page", "1")),
        )
    except PermissionError:
        raise PermissionDenied from None
    except AccountAdministrationQueryError as exc:
        presentation = admin_users_presentation(
            actor_id=request.account_id,
            keyword="",
            status="",
            page=1,
        )
        page_error = str(exc)
        status_code = 422
    response = render(
        request,
        "administration/users.html",
        {
            "presentation": presentation,
            "filter_form": filter_form,
            "confirmation_kind": confirmation_kind,
            "confirmation_target": confirmation_target,
            "confirmation_form": confirmation_form,
            "dialog": _dialog(
                confirmation_kind,
                confirmation_target,
                confirmation_form,
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _action_error(request, *, kind: str, form, message: str) -> HttpResponse:
    form.add_error(None, message)
    try:
        target = admin_user_target(
            actor_id=request.account_id,
            account_id=request.POST.get("account_id", ""),
        )
    except AccountAdministrationQueryError:
        return _render(request, status_code=422, page_error=message)
    return _render(
        request,
        status_code=422,
        confirmation_kind=kind,
        confirmation_target=target,
        confirmation_form=form,
    )


def _meta(request: HttpRequest) -> dict[str, object]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
        "audit_writer": record_audit_entry,
    }


def _post(request: HttpRequest) -> HttpResponse:
    action = request.POST.get("action", "")
    actor_id = request.account_id
    if action == "set_author":
        form = AccountRoleConfirmationForm(request.POST)
        if not form.is_valid():
            return _action_error(
                request,
                kind="role",
                form=form,
                message="请重新确认作者角色变更。",
            )
        try:
            result = set_author_role(
                actor_id=actor_id,
                account_id=form.cleaned_data["account_id"],
                enabled=form.cleaned_data["enabled"],
                **_meta(request),
            )
        except AccountLifecycleError as exc:
            return _action_error(request, kind="role", form=form, message=str(exc))
        saved = "author-granted" if result.enabled else "author-revoked"
    elif action == "set_status":
        form = AccountStatusConfirmationForm(request.POST)
        if not form.is_valid():
            return _action_error(
                request,
                kind="status",
                form=form,
                message="请重新确认账户状态变更。",
            )
        try:
            result = set_account_enabled(
                actor_id=actor_id,
                account_id=form.cleaned_data["account_id"],
                enabled=form.cleaned_data["enabled"],
                **_meta(request),
            )
        except AccountLifecycleError as exc:
            return _action_error(request, kind="status", form=form, message=str(exc))
        saved = "enabled" if result.status == "ACTIVE" else "disabled"
    elif action == "delete":
        form = AccountDeletionConfirmationForm(request.POST)
        if not form.is_valid():
            return _action_error(
                request,
                kind="delete",
                form=form,
                message="请重新确认账户删除。",
            )
        try:
            disposition = prepare_account_deletion_disposition(
                actor_id=actor_id,
                account_id=form.cleaned_data["account_id"],
                expected_article_count=form.cleaned_data["expected_article_count"],
            )
            delete_account(
                actor_id=actor_id,
                account_id=form.cleaned_data["account_id"],
                author_disposition=disposition,
                verify_author_disposition=apply_account_deletion_disposition,
                **_meta(request),
            )
        except (AccountArticleDispositionError, AccountLifecycleError) as exc:
            return _action_error(request, kind="delete", form=form, message=str(exc))
        saved = "deleted"
    else:
        return _render(request, status_code=422, page_error="管理操作无效。")
    return redirect(f"{reverse('admin:users')}?saved={saved}")


def users(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if request.method == "POST":
        return _post(request)
    kind, target, form = _get_confirmation(request, request.account_id)
    return _render(
        request,
        confirmation_kind=kind,
        confirmation_target=target,
        confirmation_form=form,
    )


__all__ = ["users"]
