from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.administration.forms.classification import (
    SectionCreateForm,
    SectionDeleteConfirmationForm,
    SectionPageForm,
    SectionRenameConfirmationForm,
    SectionUpdateConfirmationForm,
)
from apps.content.public import (
    SectionCommandError,
    admin_section_item,
    admin_section_page,
    create_section,
    delete_section,
    rename_section,
    section_default_cover_schema_ready,
    update_section,
)
from apps.core.ids import normalize_ulid

from ..presentation.feedback import feedback_count


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


def _section(request: HttpRequest, section_id: str):
    try:
        return admin_section_item(
            actor_id=request.account_id,
            section_id=section_id,
        )
    except (LookupError, PermissionError):
        raise Http404 from None


def _confirmation(request: HttpRequest):
    kind = request.GET.get("confirm_action", "")
    if not kind:
        return "", None, None
    if kind not in {"edit", "rename", "delete"}:
        raise Http404
    section = _section(request, request.GET.get("section_id", ""))
    if kind == "edit":
        form = SectionUpdateConfirmationForm(
            initial={
                "section_id": section.id,
                "name": section.name,
                "default_cover_asset_id": section.default_cover_asset_id,
                "confirm": "section_update",
            }
        )
    elif kind == "rename":
        form = SectionRenameConfirmationForm(
            initial={
                "section_id": section.id,
                "name": section.name,
                "confirm": "section_rename",
            }
        )
    else:
        form = SectionDeleteConfirmationForm(
            initial={
                "section_id": section.id,
                "confirm": "section_delete",
            }
        )
    return kind, section, form


def _dialog(kind: str, section, form) -> dict[str, object]:
    if not kind or section is None or form is None:
        return {}
    base = {
        "return_focus_id": f"section-{kind}-{section.id}",
        "return_url": f"{reverse('admin:sections')}#section-list",
    }
    if kind == "edit":
        return base | {
            "title": "编辑文章分区",
            "description": f"更新“{section.name}”的名称和默认封面。",
            "details": (
                f"当前关联 {section.affected_article_count} 篇文章、"
                f"{section.affected_revision_count} 个修订；关联关系不会改变。"
            ),
            "action": "section_update",
            "label": "保存分区",
            "field": None,
        }
    if kind == "rename":
        return base | {
            "title": "确认重命名这个分区？",
            "description": f"“{section.name}”的公开名称将立即更新。",
            "details": (
                f"当前关联 {section.affected_article_count} 篇文章、"
                f"{section.affected_revision_count} 个修订；关联关系不会改变。"
            ),
            "action": "section_rename",
            "label": "确认重命名",
            "field": form["name"],
        }
    return base | {
        "title": "确认删除这个分区？",
        "description": (
            f"“{section.name}”当前关联 {section.affected_article_count} 篇文章、"
            f"{section.affected_revision_count} 个修订。"
        ),
        "details": (
            "文章和历史修订不会删除；所有关联会转为“未知分区”，"
            "不再出现在分区导航，但仍可从首页和标签发现。"
        ),
        "action": "section_delete",
        "label": "确认删除",
        "field": None,
    }


def _render(
    request: HttpRequest,
    *,
    status: int = 200,
    create_form=None,
    confirmation_kind: str = "",
    confirmation_section=None,
    confirmation_form=None,
    page_error: str = "",
) -> HttpResponse:
    page_form = SectionPageForm(request.GET)
    if page_form.is_valid():
        page_number = page_form.cleaned_data.get("page") or 1
    else:
        page_number = 1
    try:
        section_page = admin_section_page(
            actor_id=request.account_id, page=page_number, page_size=20
        )
    except PermissionError:
        raise PermissionDenied from None
    except ValueError as exc:
        section_page = admin_section_page(
            actor_id=request.account_id, page=1, page_size=20
        )
        page_error = str(exc)
        status = 422
    response = render(
        request,
        "administration/sections.html",
        {
            "items": section_page.items,
            "section_page": section_page,
            "pagination_query": "",
            "create_form": create_form or SectionCreateForm(),
            "confirmation_kind": confirmation_kind,
            "confirmation_form": confirmation_form,
            "dialog": _dialog(
                confirmation_kind,
                confirmation_section,
                confirmation_form,
            ),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
            "affected_articles": feedback_count(request.GET, "articles"),
            "affected_revisions": feedback_count(request.GET, "revisions"),
            "section_cover_upload_url": reverse(
                "media:upload", kwargs={"adapter": "section-cover"}
            ),
            "create_cover_preview_url": _cover_preview_url(
                (create_form or SectionCreateForm())["default_cover_asset_id"].value()
            ),
            "edit_cover_preview_url": _cover_preview_url(
                confirmation_form["default_cover_asset_id"].value()
                if confirmation_kind == "edit" and confirmation_form is not None
                else None
            ),
            "section_cover_schema_ready": section_default_cover_schema_ready(),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _post_create(request: HttpRequest) -> HttpResponse:
    form = SectionCreateForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, create_form=form)
    try:
        create_section(
            actor_id=request.account_id,
            name=form.cleaned_data["name"],
            default_cover_asset_id=form.cleaned_data["default_cover_asset_id"],
            **_meta(request),
        )
    except SectionCommandError as error:
        field = "default_cover_asset_id" if error.code.startswith("media.") else "name"
        form.add_error(field, error.safe_message)
        return _render(request, status=422, create_form=form)
    return redirect(f"{reverse('admin:sections')}?saved=created#section-list")


def _cover_preview_url(asset_id) -> str:
    if not asset_id:
        return ""
    try:
        identity = normalize_ulid(asset_id)
    except (TypeError, ValueError):
        return ""
    return reverse("media:direct-delivery", kwargs={"asset_id": identity})


def _post_update(request: HttpRequest) -> HttpResponse:
    form = SectionUpdateConfirmationForm(request.POST)
    raw_id = request.POST.get("section_id", "")
    try:
        section = _section(request, raw_id)
    except Http404:
        return _render(request, status=422, page_error="分区已不存在。")
    if not form.is_valid():
        return _render(
            request,
            status=422,
            confirmation_kind="edit",
            confirmation_section=section,
            confirmation_form=form,
        )
    try:
        update_section(
            actor_id=request.account_id,
            section_id=section.id,
            name=form.cleaned_data["name"],
            default_cover_asset_id=form.cleaned_data["default_cover_asset_id"],
            **_meta(request),
        )
    except SectionCommandError as error:
        field = "default_cover_asset_id" if error.code.startswith("media.") else "name"
        form.add_error(field, error.safe_message)
        return _render(
            request,
            status=422,
            confirmation_kind="edit",
            confirmation_section=section,
            confirmation_form=form,
        )
    return redirect(f"{reverse('admin:sections')}?saved=updated#section-list")


def _post_rename(request: HttpRequest) -> HttpResponse:
    form = SectionRenameConfirmationForm(request.POST)
    raw_id = request.POST.get("section_id", "")
    if not form.is_valid():
        try:
            section = _section(request, raw_id)
        except Http404:
            return _render(request, status=422, page_error="请重新确认分区重命名。")
        return _render(
            request,
            status=422,
            confirmation_kind="rename",
            confirmation_section=section,
            confirmation_form=form,
        )
    try:
        section = _section(request, str(form.cleaned_data["section_id"]))
    except Http404:
        return _render(request, status=422, page_error="分区已不存在。")
    try:
        rename_section(
            actor_id=request.account_id,
            section_id=section.id,
            name=form.cleaned_data["name"],
            **_meta(request),
        )
    except SectionCommandError as error:
        form.add_error("name", error.safe_message)
        return _render(
            request,
            status=422,
            confirmation_kind="rename",
            confirmation_section=section,
            confirmation_form=form,
        )
    return redirect(f"{reverse('admin:sections')}?saved=renamed#section-list")


def _post_delete(request: HttpRequest) -> HttpResponse:
    form = SectionDeleteConfirmationForm(request.POST)
    if not form.is_valid():
        return _render(request, status=422, page_error="请重新确认分区删除。")
    try:
        section = _section(request, str(form.cleaned_data["section_id"]))
    except Http404:
        return _render(request, status=422, page_error="分区已不存在。")
    try:
        result = delete_section(
            actor_id=request.account_id,
            section_id=section.id,
            **_meta(request),
        )
    except SectionCommandError as error:
        return _render(request, status=422, page_error=error.safe_message)
    return redirect(
        f"{reverse('admin:sections')}?saved=deleted"
        f"&articles={section.affected_article_count}"
        f"&revisions={result.affected_revision_count}#section-list"
    )


def sections(request: HttpRequest) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    if not section_default_cover_schema_ready():
        return _render(
            request,
            status=503,
            page_error="分区默认封面迁移尚未完成，分区管理暂时只读。",
        )
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "section_create":
            return _post_create(request)
        if action == "section_rename":
            return _post_rename(request)
        if action == "section_update":
            return _post_update(request)
        if action == "section_delete":
            return _post_delete(request)
        return _render(request, status=422, page_error="分区管理操作无效。")
    kind, section, form = _confirmation(request)
    return _render(
        request,
        confirmation_kind=kind,
        confirmation_section=section,
        confirmation_form=form,
    )


__all__ = ["sections"]
