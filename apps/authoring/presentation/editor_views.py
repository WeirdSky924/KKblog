import json
from urllib.parse import urlencode

from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.authoring.forms import (
    ArticleEditorForm,
    CloudDraftDiscardForm,
    EditConflictResolutionForm,
)
from apps.authoring.presenters import (
    FORMAT_LABELS,
    conflict_workspace,
    initial_from_session,
    preview_from_form,
)
from apps.content.public import (
    ArticleBodyLimit,
    ArticleNotFound,
    ArticlePreviewError,
    CloudDraftDiscardError,
    ContentCommandError,
    ContentFormat,
    EditConflictError,
    EditTokenError,
    PublicationCommandError,
    article_for_author,
    create_article,
    discard_cloud_draft,
    open_edit_session,
    preview_article_body,
    republish_saved_revision,
    resolve_edit_conflict,
    revision_timeline,
    save_revision_with_token,
    section_list,
    selectable_tag_list,
)
from apps.core.ids import new_ulid, normalize_ulid

from .access import author_id_or_response, private_response

_DISCARD_CONFIRM = "discard-cloud-draft"
_DISCARD_ERRORS = {
    "invalid": "删除请求已失效，请关闭确认框后重试。",
    "content.edit_conflict.v1": "文章版本已发生变化，请重新打开后再试。",
    "content.edit_conflict_unresolved.v1": "请先解决编辑冲突后再继续。",
    "content.cloud_draft_scheduled.v1": "定时发布内容需先取消排期。",
    "content.cloud_draft_missing.v1": "当前没有可删除的云端草稿。",
}
_CONFLICT_ERROR = "冲突选择已失效，请刷新页面后重试。"


def _choices() -> dict:
    return {"sections": section_list(), "tags": selectable_tag_list()}


def _editor_context(
    *,
    form,
    actor_id,
    content_format: str,
    mode: str,
    article_id: str = "",
    saved: bool = False,
    cloud_error: bool = False,
    frozen: bool = False,
    row_version: int | None = None,
    can_discard_cloud_draft: bool = False,
    discard_open: bool = False,
    discard_error: str = "",
    conflict=None,
    conflict_form=None,
    conflict_error: str = "",
    skip_local_restore: bool = False,
    conflict_local_baseline: str = "",
    conflict_resolved_sequence: int | None = None,
    auto_published: bool = False,
    auto_publish_error: str = "",
) -> dict:
    preview, preview_error = preview_from_form(form, content_format)
    upload_scope = form["upload_scope"].value() or ""
    query = urlencode({"target": upload_scope})
    discard_form = (
        CloudDraftDiscardForm(
            initial={"expected_row_version": row_version, "confirm": "discard"}
        )
        if can_discard_cloud_draft and row_version is not None
        else None
    )
    return {
        "editor_form": form,
        "editor_mode": mode,
        "editor_article_id": article_id,
        "editor_actor_id": str(actor_id),
        "editor_article_key": article_id or upload_scope,
        "editor_baseline_revision_id": form["baseline_revision_id"].value(),
        "editor_format": content_format,
        "editor_format_label": FORMAT_LABELS[content_format],
        "editor_preview": preview,
        "editor_preview_error": preview_error,
        "editor_saved": saved,
        "editor_cloud_error": cloud_error,
        "editor_frozen": frozen,
        "editor_discard_form": discard_form,
        "editor_discard_open": discard_open and discard_form is not None,
        "editor_discard_error": discard_error if discard_form is not None else "",
        "editor_discard_url": (
            reverse("authoring:discard-draft", kwargs={"article_id": article_id})
            if discard_form is not None
            else ""
        ),
        "editor_conflict": conflict,
        "editor_conflict_form": conflict_form,
        "editor_conflict_error": conflict_error,
        "editor_conflict_url": (
            reverse(
                "authoring:resolve-conflict",
                kwargs={"article_id": article_id},
            )
            if conflict_form is not None
            else ""
        ),
        "editor_skip_local_restore": skip_local_restore,
        "editor_conflict_local_baseline": conflict_local_baseline,
        "editor_conflict_resolved_sequence": conflict_resolved_sequence,
        "editor_auto_published": auto_published,
        "editor_auto_publish_error": auto_publish_error,
        "editor_body_limit": ArticleBodyLimit.configured().maximum_bytes,
        "cover_upload_url": (
            f"{reverse('media:upload', kwargs={'adapter': 'article-cover'})}?{query}"
        ),
        "body_upload_url": (
            f"{reverse('media:upload', kwargs={'adapter': 'article-body'})}?{query}"
        ),
        "cover_preview_url": (
            f"/_kaj/media/{form['cover_asset_id'].value()}"
            if form["cover_asset_id"].value()
            else ""
        ),
    }


def _conflict_context(*, actor_id, conflict, session, error: str = "") -> dict:
    workspace = conflict_workspace(
        conflict,
        revision_timeline(actor_id=actor_id, article_id=conflict.article_id),
    )
    form = EditConflictResolutionForm(
        initial={
            "conflict_token": session.token,
            "local_baseline_revision_id": conflict.baseline.revision_id,
            "selected_revision_id": conflict.current.revision_id,
            "preserve_local_input": True,
        },
        revisions=workspace.revisions,
    )
    return {
        "conflict": workspace,
        "conflict_form": form,
        "conflict_error": error,
    }


def _create_upload_scope(request) -> str:
    value = request.GET.get("scope", "")
    if not value:
        return new_ulid()
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise Http404 from None


def _render_editor(request, *, status=200, **context):
    return private_response(
        render(request, "authoring/editor.html", context, status=status)
    )


def create(request):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method not in {"GET", "POST"}:
        return private_response(HttpResponseNotAllowed(("GET", "POST")))
    if request.method == "GET" and not request.GET.get("format"):
        return private_response(render(request, "authoring/create.html"))
    selected_format = (
        request.POST.get("content_format", "")
        if request.method == "POST"
        else request.GET.get("format", "")
    )
    if selected_format not in {ContentFormat.MARKDOWN, ContentFormat.TIPTAP_JSON}:
        raise Http404
    choices = _choices()
    if request.method == "GET":
        initial_body = (
            ""
            if selected_format == ContentFormat.MARKDOWN
            else '{"type":"doc","content":[]}'
        )
        form = ArticleEditorForm(
            initial={
                "content_format": selected_format,
                "upload_scope": _create_upload_scope(request),
                "baseline_revision_id": "NEW",
                "title": "",
                "body": initial_body,
                "summary_mode": "AUTO",
                "visibility": "PUBLIC",
                "comments_enabled": True,
            },
            locked_format=selected_format,
            **choices,
        )
        return _render_editor(
            request,
            **_editor_context(
                form=form,
                actor_id=actor_id,
                content_format=selected_format,
                mode="create",
            ),
        )
    form = ArticleEditorForm(
        request.POST,
        locked_format=selected_format,
        **choices,
    )
    if form.is_valid():
        try:
            created = create_article(actor_id=actor_id, snapshot=form.snapshot())
        except ContentCommandError as exc:
            form.add_error(None, exc.safe_message)
        else:
            return redirect(
                f"{reverse('authoring:edit', kwargs={'article_id': created.article_id})}"
                "?created=1"
            )
    return _render_editor(
        request,
        status=422,
        **_editor_context(
            form=form,
            actor_id=actor_id,
            content_format=selected_format,
            mode="create",
            cloud_error=True,
        ),
    )


def edit(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method not in {"GET", "POST"}:
        return private_response(HttpResponseNotAllowed(("GET", "POST")))
    try:
        article = article_for_author(actor_id=actor_id, article_id=article_id)
    except ArticleNotFound:
        raise Http404 from None
    if not article.can_edit:
        raise Http404
    choices = _choices()
    if request.method == "GET":
        try:
            session = open_edit_session(actor_id=actor_id, article_id=article_id)
        except EditConflictError as exc:
            session = exc.session
            form = ArticleEditorForm(
                initial=initial_from_session(session),
                locked_format=article.content_format,
                **choices,
            )
            conflict = _conflict_context(
                actor_id=actor_id,
                conflict=exc.conflict,
                session=session,
                error=(
                    _CONFLICT_ERROR
                    if request.GET.get("conflict_error") == "invalid"
                    else ""
                ),
            )
            return _render_editor(
                request,
                status=409,
                **_editor_context(
                    form=form,
                    actor_id=actor_id,
                    content_format=article.content_format,
                    mode="edit",
                    article_id=article_id,
                    frozen=True,
                    row_version=article.row_version,
                    conflict=conflict["conflict"],
                    conflict_form=conflict["conflict_form"],
                    conflict_error=conflict["conflict_error"],
                ),
            )
        except EditTokenError:
            raise Http404 from None
        form = ArticleEditorForm(
            initial=initial_from_session(session),
            locked_format=article.content_format,
            **choices,
        )
        return _render_editor(
            request,
            **_editor_context(
                form=form,
                actor_id=actor_id,
                content_format=article.content_format,
                mode="edit",
                article_id=article_id,
                saved=request.GET.get("created") == "1",
                row_version=session.row_version,
                can_discard_cloud_draft=article.can_discard_cloud_draft,
                discard_open=request.GET.get("confirm") == _DISCARD_CONFIRM,
                discard_error=_DISCARD_ERRORS.get(
                    request.GET.get("discard_error", ""), ""
                ),
            ),
        )
    form = ArticleEditorForm(
        request.POST,
        locked_format=article.content_format,
        **choices,
    )
    frozen = False
    conflict_state = {
        "conflict": None,
        "conflict_form": None,
        "conflict_error": "",
    }
    if form.is_valid():
        try:
            result = save_revision_with_token(
                actor_id=actor_id,
                article_id=article_id,
                edit_token=form.cleaned_data["edit_token"],
                snapshot=form.snapshot(),
            )
        except ContentCommandError as exc:
            form.add_error(None, exc.safe_message)
        except EditConflictError as exc:
            conflict_state = _conflict_context(
                actor_id=actor_id,
                conflict=exc.conflict,
                session=exc.session,
            )
            frozen = True
        except EditTokenError as exc:
            form.add_error(None, str(exc))
            frozen = True
        else:
            auto_published = False
            auto_publish_error = ""
            if article.published_revision_id is not None:
                if request.account.auto_republish_enabled:
                    try:
                        republished = republish_saved_revision(
                            actor_id=actor_id,
                            article_id=article_id,
                            revision_id=result.write.revision_id,
                            expected_row_version=result.write.row_version,
                            auto_republish_enabled=True,
                            trace_code=getattr(request, "trace_code", ""),
                        )
                    except PublicationCommandError as exc:
                        if exc.code != "content.final_review_required.v1":
                            auto_publish_error = exc.safe_message
                    else:
                        auto_published = republished.published
            saved_article = article_for_author(
                actor_id=actor_id,
                article_id=article_id,
            )
            form = ArticleEditorForm(
                initial=initial_from_session(result.next_session),
                locked_format=article.content_format,
                **choices,
            )
            response = _render_editor(
                request,
                **_editor_context(
                    form=form,
                    actor_id=actor_id,
                    content_format=article.content_format,
                    mode="edit",
                    article_id=article_id,
                    saved=True,
                    row_version=result.next_session.row_version,
                    can_discard_cloud_draft=(saved_article.can_discard_cloud_draft),
                    auto_published=auto_published,
                    auto_publish_error=auto_publish_error,
                ),
            )
            if auto_published and request.headers.get("HX-Request") == "true":
                response.headers["HX-Trigger-After-Swap"] = json.dumps(
                    {
                        "kaj:author-draft-clear": {
                            "userId": str(actor_id),
                            "articleKey": article_id,
                        }
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
            return response
    return _render_editor(
        request,
        status=409 if frozen else 422,
        **_editor_context(
            form=form,
            actor_id=actor_id,
            content_format=article.content_format,
            mode="edit",
            article_id=article_id,
            cloud_error=not frozen,
            frozen=frozen,
            row_version=article.row_version,
            can_discard_cloud_draft=(article.can_discard_cloud_draft and not frozen),
            conflict=conflict_state["conflict"],
            conflict_form=conflict_state["conflict_form"],
            conflict_error=conflict_state["conflict_error"],
        ),
    )


def _conflict_resolution_error(
    request,
    *,
    article_id: str,
    message: str,
    status: int,
):
    if request.headers.get("HX-Request") != "true":
        query = urlencode({"conflict_error": "invalid"})
        return redirect(
            f"{reverse('authoring:edit', kwargs={'article_id': article_id})}?{query}"
        )
    response = render(
        request,
        "authoring/partials/conflict_resolution_error.html",
        {"conflict_error": message},
        status=status,
    )
    response.headers["HX-Retarget"] = "#edit-conflict-feedback"
    response.headers["HX-Reswap"] = "innerHTML"
    response.headers["X-Kaj-Inline-Error"] = "true"
    return private_response(response)


def resolve_conflict(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    try:
        article = article_for_author(actor_id=actor_id, article_id=article_id)
        timeline = revision_timeline(actor_id=actor_id, article_id=article_id)
    except ArticleNotFound:
        raise Http404 from None
    if not article.can_edit:
        raise Http404
    form = EditConflictResolutionForm(request.POST, revisions=timeline)
    if not form.is_valid():
        return _conflict_resolution_error(
            request,
            article_id=article_id,
            message=_CONFLICT_ERROR,
            status=422,
        )
    try:
        session = resolve_edit_conflict(
            actor_id=actor_id,
            article_id=article_id,
            conflict_token=form.cleaned_data["conflict_token"],
            selected_revision_id=form.cleaned_data["selected_revision_id"],
        )
    except EditTokenError:
        return _conflict_resolution_error(
            request,
            article_id=article_id,
            message=_CONFLICT_ERROR,
            status=409,
        )
    selected = next(
        item
        for item in timeline
        if item.revision_id == form.cleaned_data["selected_revision_id"]
    )
    article = article_for_author(actor_id=actor_id, article_id=article_id)
    editor_form = ArticleEditorForm(
        initial=initial_from_session(session),
        locked_format=article.content_format,
        **_choices(),
    )
    return _render_editor(
        request,
        **_editor_context(
            form=editor_form,
            actor_id=actor_id,
            content_format=article.content_format,
            mode="edit",
            article_id=article_id,
            row_version=session.row_version,
            can_discard_cloud_draft=article.can_discard_cloud_draft,
            skip_local_restore=True,
            conflict_local_baseline=(
                form.cleaned_data["local_baseline_revision_id"]
                if form.cleaned_data["preserve_local_input"]
                else ""
            ),
            conflict_resolved_sequence=selected.sequence,
        ),
    )


def _discard_error_response(request, *, article_id: str, code: str, message: str):
    if request.headers.get("HX-Request") != "true":
        query = urlencode({"confirm": _DISCARD_CONFIRM, "discard_error": code})
        return redirect(
            f"{reverse('authoring:edit', kwargs={'article_id': article_id})}?{query}"
        )
    status = 409 if code.startswith("content.edit_conflict") else 422
    response = render(
        request,
        "authoring/partials/discard_cloud_draft_error.html",
        {"discard_error": message},
        status=status,
    )
    response.headers["HX-Retarget"] = "#discard-cloud-draft-feedback"
    response.headers["HX-Reswap"] = "innerHTML"
    response.headers["X-Kaj-Inline-Error"] = "true"
    return private_response(response)


def discard_draft(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    form = CloudDraftDiscardForm(request.POST)
    if not form.is_valid():
        return _discard_error_response(
            request,
            article_id=article_id,
            code="invalid",
            message=_DISCARD_ERRORS["invalid"],
        )
    try:
        result = discard_cloud_draft(
            actor_id=actor_id,
            article_id=article_id,
            expected_row_version=form.cleaned_data["expected_row_version"],
        )
    except CloudDraftDiscardError as exc:
        if exc.code == "content.cloud_draft_discard_not_allowed.v1":
            raise Http404 from None
        return _discard_error_response(
            request,
            article_id=article_id,
            code=exc.code,
            message=exc.safe_message,
        )
    if request.headers.get("HX-Request") != "true":
        return redirect(f"{reverse('authoring:articles')}?state=DRAFT&discarded=1")
    response = render(
        request,
        "authoring/partials/draft_discarded.html",
        {"draft_discard_result": result},
    )
    response.headers["HX-Trigger-After-Swap"] = json.dumps(
        {
            "kaj:author-draft-clear": {
                "userId": str(actor_id),
                "articleKey": result.article_id,
            }
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return private_response(response)


def preview(request):
    _, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    content_format = request.POST.get("content_format", "")
    source = request.POST.get("body", "")
    try:
        body = (
            source if content_format == ContentFormat.MARKDOWN else json.loads(source)
        )
        rendered = preview_article_body(content_format=content_format, body=body)
    except (ArticlePreviewError, json.JSONDecodeError, TypeError) as exc:
        message = getattr(exc, "safe_message", "正文格式不合法，无法生成预览。")
        response = render(
            request,
            "authoring/partials/editor_preview.html",
            {"editor_preview_error": message},
            status=422,
        )
        response.headers["X-Kaj-Inline-Error"] = "true"
    else:
        response = render(
            request,
            "authoring/partials/editor_preview.html",
            {
                "editor_preview": rendered,
                "editor_preview_title": request.POST.get("title", "").strip(),
            },
        )
    return private_response(response)
