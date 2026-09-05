from urllib.parse import urlencode

from django.core import signing
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.authoring.forms import PublicationReviewForm, RestoreRevisionForm
from apps.authoring.presenters import (
    publication_review_page,
    version_preview,
    version_rows,
)
from apps.content.public import (
    ArticleNotFound,
    PublicationCommandError,
    RestoreCommandError,
    article_for_author,
    cancel_schedule,
    prepare_publication,
    prepare_restore_revision,
    publish_article,
    restore_revision,
    revision_timeline,
    schedule_article,
)
from apps.core.time import to_shanghai

from .access import author_id_or_response, private_response

_RECEIPT_SALT = "kaj.authoring.publication-result.v1"
_RECEIPT_MAX_AGE = 10 * 60


def _page_number(value) -> int:
    try:
        return max(1, int(value)) if not isinstance(value, bool) else 1
    except (TypeError, ValueError):
        return 1


def _article(actor_id, article_id):
    try:
        article = article_for_author(actor_id=actor_id, article_id=article_id)
    except ArticleNotFound:
        raise Http404 from None
    if not article.can_publish:
        raise Http404
    return article


def _prepare(actor_id, article_id):
    article = _article(actor_id, article_id)
    review = prepare_publication(
        actor_id=actor_id,
        article_id=article_id,
        revision_id=article.revision_id,
        expected_row_version=article.row_version,
    )
    return article, publication_review_page(article_id=article_id, review=review)


def _form(review, data=None):
    review_values = {
        "revision_id": review.revision_id,
        "expected_row_version": review.row_version,
        "review_token": review.review_token,
    }
    if data is None:
        return PublicationReviewForm(
            initial={**review_values, "publication_mode": "IMMEDIATE"}
        )
    rebound = data.copy()
    for name, value in review_values.items():
        rebound[name] = value
    form = PublicationReviewForm(rebound)
    form.is_valid()
    if form.errors.get("scheduled_local"):
        form.fields["scheduled_local"].widget.attrs["data-error-focus"] = ""
    return form


def _render_review(
    request,
    *,
    article_id,
    review=None,
    form=None,
    error="",
    restored=False,
    status=200,
):
    return private_response(
        render(
            request,
            "authoring/review.html",
            {
                "review": review,
                "review_form": form,
                "review_error": error,
                "review_restored": restored,
                "editor_article_id": article_id,
            },
            status=status,
        )
    )


def _error_status(code: str) -> int:
    return 409 if "conflict" in code or "token" in code else 422


def _receipt(*, actor_id, article_id, revision_id, mode):
    return signing.dumps(
        {
            "actor_id": str(actor_id),
            "article_id": article_id,
            "revision_id": revision_id,
            "mode": mode,
        },
        salt=_RECEIPT_SALT,
        compress=True,
    )


def review(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method not in {"GET", "POST"}:
        return private_response(HttpResponseNotAllowed(("GET", "POST")))
    if request.method == "GET":
        try:
            _, page = _prepare(actor_id, article_id)
        except PublicationCommandError as exc:
            return _render_review(
                request,
                article_id=article_id,
                error=exc.safe_message,
                status=_error_status(exc.code),
            )
        return _render_review(
            request,
            article_id=article_id,
            review=page,
            form=_form(page),
            restored=request.GET.get("restored") == "1",
        )

    form = PublicationReviewForm(request.POST)
    if not form.is_valid():
        try:
            _, page = _prepare(actor_id, article_id)
        except PublicationCommandError as exc:
            return _render_review(
                request,
                article_id=article_id,
                error=exc.safe_message,
                status=_error_status(exc.code),
            )
        return _render_review(
            request,
            article_id=article_id,
            review=page,
            form=_form(page, request.POST),
            status=422,
        )
    values = form.cleaned_data
    try:
        if values["publication_mode"] == "IMMEDIATE":
            result = publish_article(
                actor_id=actor_id,
                article_id=article_id,
                revision_id=values["revision_id"],
                expected_row_version=values["expected_row_version"],
                review_token=values["review_token"],
                trace_code=getattr(request, "trace_code", ""),
            )
        else:
            result = schedule_article(
                actor_id=actor_id,
                article_id=article_id,
                revision_id=values["revision_id"],
                expected_row_version=values["expected_row_version"],
                review_token=values["review_token"],
                scheduled_local=values["scheduled_local"],
                trace_code=getattr(request, "trace_code", ""),
            )
    except PublicationCommandError as exc:
        try:
            _, page = _prepare(actor_id, article_id)
        except PublicationCommandError:
            return _render_review(
                request,
                article_id=article_id,
                error=exc.safe_message,
                status=_error_status(exc.code),
            )
        next_form = _form(page, request.POST)
        field = "scheduled_local" if "schedule_time" in exc.code else None
        next_form.add_error(field, exc.safe_message)
        return _render_review(
            request,
            article_id=article_id,
            review=page,
            form=next_form,
            status=_error_status(exc.code),
        )
    token = _receipt(
        actor_id=actor_id,
        article_id=result.article_id,
        revision_id=result.revision_id,
        mode=values["publication_mode"],
    )
    url = reverse("authoring:publication-result", args=(article_id,))
    return redirect(f"{url}?receipt={token}")


def publication_result(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "GET":
        return private_response(HttpResponseNotAllowed(("GET",)))
    try:
        receipt = signing.loads(
            request.GET.get("receipt", ""),
            salt=_RECEIPT_SALT,
            max_age=_RECEIPT_MAX_AGE,
        )
    except signing.BadSignature:
        raise Http404 from None
    article = _article(actor_id, article_id)
    if (
        receipt.get("actor_id") != str(actor_id)
        or receipt.get("article_id") != article_id
        or receipt.get("revision_id") != article.revision_id
        or receipt.get("mode") not in {"IMMEDIATE", "SCHEDULED"}
    ):
        raise Http404
    immediate = receipt["mode"] == "IMMEDIATE"
    if immediate:
        valid = (
            article.publication_state == "PUBLISHED"
            and article.published_revision_id == article.revision_id
        )
    else:
        valid = (
            article.publication_state == "SCHEDULED"
            and article.scheduled_revision_id == article.revision_id
            and article.scheduled_for is not None
        )
    if not valid:
        raise Http404
    return private_response(
        render(
            request,
            "authoring/publication_result.html",
            {
                "article": article,
                "publication_immediate": immediate,
                "editor_article_id": article_id,
                "draft_clear_user_id": str(actor_id) if immediate else "",
                "scheduled_for_local": (
                    to_shanghai(article.scheduled_for) if not immediate else None
                ),
            },
        )
    )


def cancel_article_schedule(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    try:
        result = cancel_schedule(
            actor_id=actor_id,
            article_id=article_id,
            trace_code=getattr(request, "trace_code", ""),
        )
    except PublicationCommandError:
        raise Http404 from None
    state = "DRAFT" if result.cancelled else result.publication_state
    return redirect(f"{reverse('authoring:articles')}?state={state}&cancelled=1")


def _versions_context(
    *,
    actor_id,
    article_id: str,
    selected_id: str = "",
    page: int = 1,
    restore_error: str = "",
):
    article = _article(actor_id, article_id)
    try:
        timeline = revision_timeline(
            actor_id=actor_id,
            article_id=article_id,
            page=page,
            page_size=20,
        )
    except ArticleNotFound:
        raise Http404 from None
    rows = version_rows(timeline.items)
    selected = None
    restore_form = None
    if selected_id:
        row = next((item for item in rows if item.revision_id == selected_id), None)
        if row is None:
            try:
                full_timeline = revision_timeline(
                    actor_id=actor_id,
                    article_id=article_id,
                )
            except ArticleNotFound:
                raise Http404 from None
            row = next(
                (
                    item
                    for item in version_rows(full_timeline)
                    if item.revision_id == selected_id
                ),
                None,
            )
            if row is None:
                raise Http404
        try:
            source = prepare_restore_revision(
                actor_id=actor_id,
                article_id=article_id,
                source_revision_id=selected_id,
            )
        except RestoreCommandError as exc:
            restore_error = exc.safe_message
        else:
            selected = version_preview(source, can_restore=not row.is_working)
            restore_form = RestoreRevisionForm(
                initial={
                    "source_revision_id": source.source_revision_id,
                    "expected_row_version": source.row_version,
                    "restore_token": source.token,
                }
            )
    return {
        "article": article,
        "versions": rows,
        "version_page": timeline,
        "pagination_query": urlencode({"revision": selected_id}) if selected_id else "",
        "selected_version": selected,
        "restore_form": restore_form,
        "restore_error": restore_error,
        "editor_article_id": article_id,
    }


def versions(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "GET":
        return private_response(HttpResponseNotAllowed(("GET",)))
    return private_response(
        render(
            request,
            "authoring/versions.html",
            _versions_context(
                actor_id=actor_id,
                article_id=article_id,
                selected_id=request.GET.get("revision", ""),
                page=_page_number(request.GET.get("page")),
            ),
        )
    )


def restore_version(request, article_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    form = RestoreRevisionForm(request.POST)
    if not form.is_valid():
        return private_response(
            render(
                request,
                "authoring/versions.html",
                _versions_context(
                    actor_id=actor_id,
                    article_id=article_id,
                    selected_id=request.POST.get("source_revision_id", ""),
                    restore_error="恢复请求已失效，请重新选择版本。",
                ),
                status=422,
            )
        )
    values = form.cleaned_data
    try:
        timeline = revision_timeline(actor_id=actor_id, article_id=article_id)
    except ArticleNotFound:
        raise Http404 from None
    rows = version_rows(timeline)
    selected = next(
        (item for item in rows if item.revision_id == values["source_revision_id"]),
        None,
    )
    if selected is None or selected.is_working:
        raise Http404
    try:
        restore_revision(
            actor_id=actor_id,
            article_id=article_id,
            source_revision_id=values["source_revision_id"],
            expected_row_version=values["expected_row_version"],
            restore_token=values["restore_token"],
        )
    except RestoreCommandError as exc:
        return private_response(
            render(
                request,
                "authoring/versions.html",
                _versions_context(
                    actor_id=actor_id,
                    article_id=article_id,
                    selected_id=values["source_revision_id"],
                    restore_error=exc.safe_message,
                ),
                status=_error_status(exc.code),
            )
        )
    return redirect(f"{reverse('authoring:review', args=(article_id,))}?restored=1")
