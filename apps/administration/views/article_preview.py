from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.accounts.public import is_administrator
from apps.content.public import (
    ArticleNotFound,
    admin_article_item,
    admin_published_revision_history,
    article_for_admin,
    article_published_revision_for_admin,
)


def article_preview_context(
    request: HttpRequest,
    *,
    article_id: str,
    revision: str,
    revision_id: str = "",
) -> dict[str, object]:
    if revision not in {"working", "published"}:
        raise ArticleNotFound
    try:
        item = admin_article_item(
            actor_id=request.account_id,
            article_id=article_id,
        )
    except (LookupError, PermissionError):
        raise ArticleNotFound from None
    history = ()
    selected_publication = None
    if revision == "working":
        detail = article_for_admin(
            actor_id=request.account_id,
            article_id=article_id,
            revision="working",
            trace_code=getattr(request, "trace_code", ""),
        )
    else:
        try:
            history = admin_published_revision_history(
                actor_id=request.account_id,
                article_id=article_id,
            )
        except (LookupError, PermissionError):
            raise ArticleNotFound from None
        if not history:
            detail = None
        else:
            selected_id = revision_id or history[0].revision_id
            selected_publication = next(
                (item for item in history if item.revision_id == selected_id),
                None,
            )
            if selected_publication is None:
                raise ArticleNotFound
            detail = article_published_revision_for_admin(
                actor_id=request.account_id,
                article_id=article_id,
                revision_id=selected_publication.revision_id,
                trace_code=getattr(request, "trace_code", ""),
            )
    return {
        "preview_article": item,
        "preview_detail": detail,
        "preview_history": history,
        "preview_mode": revision,
        "preview_selected_publication": selected_publication,
        "preview_url": reverse("admin:article-preview", args=(article_id,)),
    }


def article_preview(request: HttpRequest, article_id: str) -> HttpResponse:
    if not is_administrator(getattr(request, "account_id", None)):
        raise PermissionDenied
    try:
        context = article_preview_context(
            request,
            article_id=article_id,
            revision=request.GET.get("revision", "working"),
            revision_id=request.GET.get("revision_id", ""),
        )
    except ArticleNotFound:
        response = render(
            request,
            "administration/partials/article_preview_content.html",
            {"preview_error": "文章或所选发布版本已不可用。"},
            status=404,
        )
        response.headers["X-Kaj-Inline-Error"] = "true"
    else:
        response = render(
            request,
            "administration/partials/article_preview_content.html",
            context,
        )
    response.headers["Cache-Control"] = "no-store"
    return response


__all__ = ["article_preview", "article_preview_context"]
