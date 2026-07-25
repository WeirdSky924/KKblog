from django.urls import path

from apps.administration.views.article_moderation import (
    create_article_case_action,
    restore_article_case_action,
    review_article_appeal_action,
)
from apps.administration.views.audit import audit_log
from apps.administration.views.invites import invites
from apps.administration.views.ip_blocks import ip_blocks

app_name = "admin"

urlpatterns = [
    path(
        "articles/<str:article_id>/moderation/",
        create_article_case_action,
        name="article-case-create",
    ),
    path(
        "article-cases/<str:case_id>/restore/",
        restore_article_case_action,
        name="article-case-restore",
    ),
    path(
        "article-appeals/<str:appeal_id>/review/",
        review_article_appeal_action,
        name="article-appeal-review",
    ),
    path("audit/", audit_log, name="audit"),
    path("invites/", invites, name="invites"),
    path("ip-blocks/", ip_blocks, name="ip-blocks"),
]
