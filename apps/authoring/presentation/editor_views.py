import json
from urllib.parse import urlencode

from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.authoring.forms import ArticleEditorForm
from apps.authoring.presenters import (
    FORMAT_LABELS,
    initial_from_session,
    preview_from_form,
)
from apps.content.public import (
    ArticleBodyLimit,
    ArticleNotFound,
    ArticlePreviewError,
    ContentCommandError,
    ContentFormat,
    EditConflictError,
    EditTokenError,
    article_for_author,
    create_article,
    open_edit_session,
    preview_article_body,
    save_revision_with_token,
    section_list,
    selectable_tag_list,
)
from apps.core.ids import new_ulid, normalize_ulid

from .access import author_id_or_response, private_response


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
) -> dict:
    preview, preview_error = preview_from_form(form, content_format)
    upload_scope = form["upload_scope"].value() or ""
    query = urlencode({"target": upload_scope})
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
            ),
        )
    form = ArticleEditorForm(
        request.POST,
        locked_format=article.content_format,
        **choices,
    )
    frozen = False
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
        except (EditTokenError, EditConflictError) as exc:
            form.add_error(None, str(exc))
            frozen = True
        else:
            form = ArticleEditorForm(
                initial=initial_from_session(result.next_session),
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
                    saved=True,
                ),
            )
    return _render_editor(
        request,
        status=409 if frozen else 422,
        **_editor_context(
            form=form,
            actor_id=actor_id,
            content_format=article.content_format,
            mode="edit",
            article_id=article_id,
            cloud_error=True,
            frozen=frozen,
        ),
    )


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
