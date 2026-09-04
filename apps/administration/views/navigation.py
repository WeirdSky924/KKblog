from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.administration.forms.navigation import (
    NavigationDeleteConfirmationForm,
    NavigationMoveForm,
    NavigationNodeCreateForm,
    NavigationNodeEditConfirmationForm,
    NavigationVisibilityConfirmationForm,
)
from apps.administration.presentation.navigation import (
    AdminNavigationRow,
    admin_navigation_rows,
)
from apps.content.public import section_list
from apps.navigation.public import (
    NavigationCommandError,
    NavigationTreeQueryError,
    admin_navigation_tree,
    create_navigation_node,
    delete_navigation_subtree,
    edit_navigation_node,
    move_navigation_subtree,
    set_navigation_node_hidden,
)

from ..presentation.feedback import feedback_count

VALID_CONFIRMATIONS = {"edit", "hide", "show", "delete"}
EDIT_FORM_PREFIX = "navigation_edit"


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


def _section_choices():
    return tuple((str(item.section_id), item.name) for item in section_list())


def _parent_choices(tree):
    return tuple(
        (
            str(item.id),
            f"{'— ' * item.depth}{item.label}",
        )
        for item in tree.flat_nodes
        if item.depth < 2
    )


def _find_row(
    rows: tuple[AdminNavigationRow, ...],
    node_id: str,
) -> AdminNavigationRow:
    for row in rows:
        if str(row.node.id) == str(node_id):
            return row
        try:
            return _find_row(row.children, node_id)
        except LookupError:
            continue
    raise LookupError


def _confirmation(request: HttpRequest, *, tree, rows):
    kind = request.GET.get("confirm_action", "")
    if not kind:
        return "", None, None
    if kind not in VALID_CONFIRMATIONS:
        raise Http404
    try:
        row = _find_row(rows, request.GET.get("node_id", ""))
    except LookupError:
        raise Http404 from None
    node = row.node
    base = {
        "node_id": node.id,
        "expected_tree_version": tree.tree_version,
    }
    if kind == "edit":
        form = NavigationNodeEditConfirmationForm(
            initial=base
            | {
                "expected_row_version": node.row_version,
                "label": node.label,
                "node_type": node.node_type,
                "target_url": node.target_url or "",
                "section_id": node.target_id or "",
                "default_expanded": node.default_expanded,
                "confirm": "navigation_edit",
            },
            section_choices=_section_choices(),
            default_expanded_enabled=bool(node.children),
            prefix=EDIT_FORM_PREFIX,
        )
    elif kind in {"hide", "show"}:
        form = NavigationVisibilityConfirmationForm(
            initial=base
            | {
                "expected_row_version": node.row_version,
                "hidden": "true" if kind == "hide" else "false",
                "confirm": "navigation_visibility",
            }
        )
    else:
        form = NavigationDeleteConfirmationForm(
            initial=base
            | {
                "expected_versions": tree.version_snapshot,
                "confirm": "navigation_delete",
            }
        )
    return kind, row, form


def _dialog(kind: str, row, form) -> dict[str, object]:
    if not kind or row is None or form is None:
        return {}
    node = row.node
    base = {
        "return_focus_id": f"navigation-{kind}-{node.id}",
        "return_url": f"{reverse('admin:navigation')}#navigation-tree",
    }
    if kind == "edit":
        return base | {
            "title": "确认编辑这个导航节点？",
            "description": f"“{node.label}”的名称、类型或目标将立即更新。",
            "details": "父级和层内位置请使用树中的移动控件调整。",
            "action": "navigation_edit",
            "label": "确认编辑",
            "form_fields": True,
        }
    if kind in {"hide", "show"}:
        action = "隐藏" if kind == "hide" else "显示"
        return base | {
            "title": f"确认{action}这个导航节点？",
            "description": f"“{node.label}”及其公开子树将{'停止展示' if kind == 'hide' else '恢复展示'}。",
            "details": f"当前子树共 {row.subtree_count} 个节点，节点记录不会删除。",
            "action": "navigation_visibility",
            "label": f"确认{action}",
            "form_fields": False,
        }
    return base | {
        "title": "确认删除这个导航子树？",
        "description": f"“{node.label}”及其 {row.subtree_count - 1} 个子节点将被删除。",
        "details": "内容页面、文章分区和外部站点不会被删除；此操作只删除主页侧边导航节点。",
        "action": "navigation_delete",
        "label": "确认删除子树",
        "form_fields": False,
    }


def _default_create_form(tree):
    return NavigationNodeCreateForm(
        initial={
            "position": len(tree.roots),
            "expected_tree_version": tree.tree_version,
        },
        section_choices=_section_choices(),
        parent_choices=_parent_choices(tree),
    )


def _tree_unavailable_response(request: HttpRequest) -> HttpResponse:
    response = render(
        request,
        "administration/navigation.html",
        {
            "tree_unavailable": True,
            "page_error": "主页侧边导航暂时不可用，请稍后重试。",
            "trace_code": getattr(request, "trace_code", ""),
        },
        status=503,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    create_form=None,
    confirmation_kind: str = "",
    confirmation_row=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    try:
        tree = admin_navigation_tree(actor_id=request.account_id)
    except PermissionError:
        raise PermissionDenied from None
    except NavigationTreeQueryError:
        return _tree_unavailable_response(request)
    rows = admin_navigation_rows(tree)
    response = render(
        request,
        "administration/navigation.html",
        {
            "tree": tree,
            "rows": rows,
            "create_form": (
                create_form if create_form is not None else _default_create_form(tree)
            ),
            "confirmation_kind": confirmation_kind,
            "confirmation_form": confirmation_form,
            "dialog": _dialog(
                confirmation_kind,
                confirmation_row,
                confirmation_form,
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "deleted_count": feedback_count(request.GET, "deleted"),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _status(error: NavigationCommandError) -> int:
    if error.code == "navigation.admin_required.v1":
        return 403
    if error.code == "navigation.edit_conflict.v1":
        return 409
    return 422


def _create_error_field(error: NavigationCommandError) -> str | None:
    if "label" in error.code:
        return "label"
    if "section_target" in error.code:
        return "section_id"
    if "target" in error.code:
        return "target_url"
    if "default_expanded" in error.code:
        return "default_expanded"
    if "parent" in error.code or "depth" in error.code or "cycle" in error.code:
        return "parent_id"
    if "position" in error.code:
        return "position"
    return None


def _tree_and_rows(request: HttpRequest):
    try:
        tree = admin_navigation_tree(actor_id=request.account_id)
    except PermissionError:
        raise PermissionDenied from None
    return tree, admin_navigation_rows(tree)


def _post_create(request: HttpRequest) -> HttpResponse:
    tree, _rows = _tree_and_rows(request)
    form = NavigationNodeCreateForm(
        request.POST,
        section_choices=_section_choices(),
        parent_choices=_parent_choices(tree),
    )
    if not form.is_valid():
        return _render(request, status=422, create_form=form)
    try:
        create_navigation_node(
            actor_id=request.account_id,
            label=form.cleaned_data["label"],
            node_type=form.cleaned_data["node_type"],
            target_url=form.cleaned_data["target_url"],
            target_id=form.cleaned_data["section_id"],
            parent_id=form.cleaned_data["parent_id"],
            position=form.cleaned_data["position"],
            expected_tree_version=form.cleaned_data["expected_tree_version"],
            default_expanded=form.cleaned_data["default_expanded"],
            **_meta(request),
        )
    except NavigationCommandError as error:
        field = _create_error_field(error)
        form.add_error(field if field in form.fields else None, error.safe_message)
        return _render(
            request,
            status=_status(error),
            create_form=form,
            page_error=(error.safe_message if _status(error) == 409 else ""),
        )
    return redirect(f"{reverse('admin:navigation')}?saved=created#navigation-tree")


def _invalid_confirmation(request, *, kind: str, node_id: str, form, message: str):
    tree, rows = _tree_and_rows(request)
    del tree
    try:
        row = _find_row(rows, node_id)
    except LookupError:
        return _render(request, status=422, page_error=message)
    return _render(
        request,
        status=422,
        confirmation_kind=kind,
        confirmation_row=row,
        confirmation_form=form,
        page_error=message,
    )


def _post_edit(request: HttpRequest) -> HttpResponse:
    raw_id = request.POST.get(f"{EDIT_FORM_PREFIX}-node_id", "")
    _tree, rows = _tree_and_rows(request)
    try:
        default_expanded_enabled = bool(_find_row(rows, raw_id).node.children)
    except LookupError:
        default_expanded_enabled = False
    form = NavigationNodeEditConfirmationForm(
        request.POST,
        section_choices=_section_choices(),
        default_expanded_enabled=default_expanded_enabled,
        prefix=EDIT_FORM_PREFIX,
    )
    if not form.is_valid():
        return _invalid_confirmation(
            request,
            kind="edit",
            node_id=raw_id,
            form=form,
            message="请重新确认导航编辑。",
        )
    try:
        edit_navigation_node(
            actor_id=request.account_id,
            node_id=form.cleaned_data["node_id"],
            expected_row_version=form.cleaned_data["expected_row_version"],
            label=form.cleaned_data["label"],
            node_type=form.cleaned_data["node_type"],
            target_url=form.cleaned_data["target_url"],
            target_id=form.cleaned_data["section_id"],
            default_expanded=form.cleaned_data["default_expanded"],
            expected_tree_version=form.cleaned_data["expected_tree_version"],
            **_meta(request),
        )
    except NavigationCommandError as error:
        if _status(error) == 409:
            return _render(request, status=409, page_error=error.safe_message)
        field = _create_error_field(error)
        form.add_error(field if field in form.fields else None, error.safe_message)
        return _invalid_confirmation(
            request,
            kind="edit",
            node_id=raw_id,
            form=form,
            message=error.safe_message,
        )
    return redirect(f"{reverse('admin:navigation')}?saved=edited#navigation-tree")


def _post_visibility(request: HttpRequest) -> HttpResponse:
    form = NavigationVisibilityConfirmationForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, page_error="请重新确认导航显隐。")
    try:
        set_navigation_node_hidden(
            actor_id=request.account_id,
            node_id=form.cleaned_data["node_id"],
            hidden=form.cleaned_data["hidden"],
            expected_row_version=form.cleaned_data["expected_row_version"],
            expected_tree_version=form.cleaned_data["expected_tree_version"],
            **_meta(request),
        )
    except NavigationCommandError as error:
        return _render(request, status=_status(error), page_error=error.safe_message)
    saved = "hidden" if form.cleaned_data["hidden"] else "shown"
    return redirect(f"{reverse('admin:navigation')}?saved={saved}#navigation-tree")


def _post_delete(request: HttpRequest) -> HttpResponse:
    form = NavigationDeleteConfirmationForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, page_error="请重新确认导航子树删除。")
    try:
        result = delete_navigation_subtree(
            actor_id=request.account_id,
            node_id=form.cleaned_data["node_id"],
            expected_versions=form.cleaned_data["expected_versions"],
            expected_tree_version=form.cleaned_data["expected_tree_version"],
            **_meta(request),
        )
    except NavigationCommandError as error:
        return _render(request, status=_status(error), page_error=error.safe_message)
    return redirect(
        f"{reverse('admin:navigation')}?saved=deleted"
        f"&deleted={result.deleted_node_count}#navigation-tree"
    )


def _post_move(request: HttpRequest) -> HttpResponse:
    form = NavigationMoveForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, page_error="导航移动参数不合法。")
    try:
        move_navigation_subtree(
            actor_id=request.account_id,
            node_id=form.cleaned_data["node_id"],
            new_parent_id=form.cleaned_data["new_parent_id"],
            new_position=form.cleaned_data["new_position"],
            expected_versions=form.cleaned_data["expected_versions"],
            expected_tree_version=form.cleaned_data["expected_tree_version"],
            **_meta(request),
        )
    except NavigationCommandError as error:
        return _render(request, status=_status(error), page_error=error.safe_message)
    return redirect(f"{reverse('admin:navigation')}?saved=moved#navigation-tree")


def navigation(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    try:
        if request.method == "POST":
            action = request.POST.get("action", "")
            if action == "navigation_create":
                return _post_create(request)
            if action == "navigation_edit":
                return _post_edit(request)
            if action == "navigation_visibility":
                return _post_visibility(request)
            if action == "navigation_delete":
                return _post_delete(request)
            if action == "navigation_move":
                return _post_move(request)
            return _render(
                request,
                status=422,
                page_error="主页侧边导航管理操作无效。",
            )
        tree, rows = _tree_and_rows(request)
        kind, row, form = _confirmation(request, tree=tree, rows=rows)
        return _render(
            request,
            confirmation_kind=kind,
            confirmation_row=row,
            confirmation_form=form,
        )
    except NavigationTreeQueryError:
        return _tree_unavailable_response(request)


__all__ = ["navigation"]
