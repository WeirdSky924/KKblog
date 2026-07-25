from django.urls import path

from .article_appeal_views import (
    create_article_appeal,
    upload_article_appeal_evidence,
)
from .views import confirm_report, create_comment_report, upload_report_evidence

app_name = "moderation"

urlpatterns = [
    path(
        "article-cases/<str:case_id>/appeal/",
        create_article_appeal,
        name="article-appeal-create",
    ),
    path(
        "article-cases/<str:case_id>/appeal/evidence/",
        upload_article_appeal_evidence,
        name="article-appeal-evidence-upload",
    ),
    path(
        "comments/<str:comment_id>/report/confirm/",
        confirm_report,
        name="report-confirm",
    ),
    path(
        "comments/<str:comment_id>/report/",
        create_comment_report,
        name="report-create",
    ),
    path(
        "comments/<str:comment_id>/report/evidence/",
        upload_report_evidence,
        name="report-evidence-upload",
    ),
]
