from django.urls import path

from apps.administration.permissions import administrator_required
from apps.administration.views.article_moderation import (
    create_article_case_action,
    restore_article_case_action,
    review_article_appeal_action,
)
from apps.administration.views.article_preview import article_preview
from apps.administration.views.articles import articles
from apps.administration.views.audit import audit_log
from apps.administration.views.comments import comments
from apps.administration.views.errors import runtime_errors
from apps.administration.views.exchange import download_export, exchange
from apps.administration.views.index import index
from apps.administration.views.invites import invites
from apps.administration.views.ip_blocks import ip_blocks
from apps.administration.views.navigation import navigation
from apps.administration.views.notifications import notifications
from apps.administration.views.opportunities import opportunities
from apps.administration.views.reports import reports
from apps.administration.views.sections import sections
from apps.administration.views.site_settings import site_settings
from apps.administration.views.tags import tags
from apps.administration.views.tasks import task_runs
from apps.administration.views.users import users
from apps.analytics.presentation.admin_view import analytics_dashboard

app_name = "admin"

urlpatterns = [
    path("", administrator_required(index), name="index"),
    path("users/", administrator_required(users), name="users"),
    path("articles/", administrator_required(articles), name="articles"),
    path(
        "articles/<str:article_id>/preview/",
        administrator_required(article_preview),
        name="article-preview",
    ),
    path("comments/", administrator_required(comments), name="comments"),
    path("reports/", administrator_required(reports), name="reports"),
    path("tags/", administrator_required(tags), name="tags"),
    path("sections/", administrator_required(sections), name="sections"),
    path("navigation/", administrator_required(navigation), name="navigation"),
    path(
        "site-settings/",
        administrator_required(site_settings),
        name="site-settings",
    ),
    path(
        "analytics/",
        administrator_required(analytics_dashboard),
        name="analytics",
    ),
    path(
        "articles/<str:article_id>/moderation/",
        administrator_required(create_article_case_action),
        name="article-case-create",
    ),
    path(
        "article-cases/<str:case_id>/restore/",
        administrator_required(restore_article_case_action),
        name="article-case-restore",
    ),
    path(
        "article-appeals/<str:appeal_id>/review/",
        administrator_required(review_article_appeal_action),
        name="article-appeal-review",
    ),
    path("audit/", administrator_required(audit_log), name="audit"),
    path("errors/", administrator_required(runtime_errors), name="errors"),
    path("tasks/", administrator_required(task_runs), name="tasks"),
    path(
        "opportunities/",
        administrator_required(opportunities),
        name="opportunities",
    ),
    path("exchange/", administrator_required(exchange), name="exchange"),
    path(
        "exchange/<str:job_id>/download/",
        administrator_required(download_export),
        name="exchange-download",
    ),
    path("invites/", administrator_required(invites), name="invites"),
    path("ip-blocks/", administrator_required(ip_blocks), name="ip-blocks"),
    path(
        "notifications/",
        administrator_required(notifications),
        name="notifications",
    ),
]
