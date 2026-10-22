from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.navigation.public import (
    ArticleExplanationSettingsQueryError,
    SiteContentCommandError,
    update_article_explanation_settings,
)
from apps.navigation.public import (
    article_explanation_settings as query_article_explanation_settings,
)

from ..forms.site_settings import ArticleExplanationSettingsForm


def _meta(request: HttpRequest) -> dict[str, str]:
    return {
        "client_ip": request.client_ip,
        "trace_code": getattr(request, "trace_code", ""),
    }


def _status(error: SiteContentCommandError) -> int:
    return 409 if "conflict" in error.code else 422


def _form(settings, *, data=None) -> ArticleExplanationSettingsForm:
    return ArticleExplanationSettingsForm(
        data=data,
        initial={
            "daily_limit": settings.daily_limit,
            "minute_limit": settings.minute_limit,
            "selection_limit": settings.selection_limit,
            "history_limit": settings.history_limit,
            "focus_idle_timeout_minutes": settings.focus_idle_timeout_minutes,
            "focus_manual_pause_limit": settings.focus_manual_pause_limit,
            "expected_version": settings.row_version,
        },
    )


def _unavailable(request: HttpRequest) -> HttpResponse:
    response = render(
        request,
        "administration/article_explanation_settings.html",
        {
            "settings_unavailable": True,
            "page_error": "文章阅读设置暂时不可用，请稍后重试。",
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
    form: ArticleExplanationSettingsForm | None = None,
    page_error: str = "",
) -> HttpResponse:
    try:
        settings = query_article_explanation_settings()
    except (ArticleExplanationSettingsQueryError, DatabaseError):
        return _unavailable(request)
    response = render(
        request,
        "administration/article_explanation_settings.html",
        {
            "article_explanation_settings": settings,
            "article_explanation_form": form or _form(settings),
            "page_error": page_error,
            "saved": request.GET.get("saved", ""),
        },
        status=status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def article_explanation_settings(request: HttpRequest) -> HttpResponse:
    try:
        current = query_article_explanation_settings()
    except (ArticleExplanationSettingsQueryError, DatabaseError):
        return _unavailable(request)

    if request.method != "POST":
        return _render(request)

    form = _form(current, data=request.POST)
    if not form.is_valid():
        return _render(
            request,
            status=422,
            form=form,
            page_error="请修正文章阅读设置。",
        )
    try:
        update_article_explanation_settings(
            actor_id=request.account_id,
            **form.cleaned_data,
            **_meta(request),
        )
    except SiteContentCommandError as error:
        form.add_error(None, error.safe_message)
        return _render(
            request,
            status=_status(error),
            form=form,
            page_error=error.safe_message,
        )
    return redirect(f"{reverse('admin:article-explanation-settings')}?saved=1")


__all__ = ["article_explanation_settings"]
